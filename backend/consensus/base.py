# backend/consensus/base.py

DEFAULT_VALIDATORS_COUNT = 5
DEFAULT_CONSENSUS_SLEEP_TIME = 5

import os
import asyncio
from collections import deque
import traceback
from typing import Callable, Iterator, List
import time
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session
from backend.consensus.vrf import get_validators_for_transaction
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.types import ConsensusData
from backend.domain.types import (
    Transaction,
    TransactionType,
    LLMProvider,
    Validator,
)
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt, Vote, ExecutionResultStatus
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)


def node_factory(
    validator: dict,
    validator_mode: ExecutionMode,
    contract_snapshot: ContractSnapshot,
    leader_receipt: Receipt | None,
    msg_handler: MessageHandler,
    contract_snapshot_factory: Callable[[str], ContractSnapshot],
) -> Node:
    return Node(
        contract_snapshot=contract_snapshot,
        validator_mode=validator_mode,
        leader_receipt=leader_receipt,
        msg_handler=msg_handler,
        validator=Validator(
            address=validator["address"],
            stake=validator["stake"],
            llmprovider=LLMProvider(
                provider=validator["provider"],
                model=validator["model"],
                config=validator["config"],
                plugin=validator["plugin"],
                plugin_config=validator["plugin_config"],
            ),
        ),
        contract_snapshot_factory=contract_snapshot_factory,
    )


def contract_snapshot_factory(
    contract_address: str,
    session: Session,
    transaction: Transaction,
):
    if (
        transaction.type == TransactionType.DEPLOY_CONTRACT
        and contract_address == transaction.to_address
    ):
        ret = ContractSnapshot(None, session)
        ret.contract_address = transaction.to_address
        ret.contract_code = transaction.data["contract_code"]
        ret.encoded_state = {}
        return ret
    return ContractSnapshot(contract_address, session)


class ConsensusAlgorithm:
    def __init__(
        self,
        get_session: Callable[[], Session],
        msg_handler: MessageHandler,
    ):
        self.get_session = get_session
        self.msg_handler = msg_handler
        self.queues: dict[str, asyncio.Queue] = {}

    def run_crawl_snapshot_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._crawl_snapshot())
        loop.close()

    async def _crawl_snapshot(self):
        while True:
            with self.get_session() as session:
                chain_snapshot = ChainSnapshot(session)
                pending_transactions = chain_snapshot.get_pending_transactions()
                for transaction in pending_transactions:
                    transaction = Transaction.from_dict(transaction)
                    address = transaction.to_address or transaction.from_address

                    if address not in self.queues:
                        self.queues[address] = asyncio.Queue()
                    await self.queues[address].put(transaction)
            await asyncio.sleep(DEFAULT_CONSENSUS_SLEEP_TIME)

    def run_consensus_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._run_consensus())
        loop.close()

    async def _run_consensus(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        # watch out! as ollama uses GPU resources and webrequest aka selenium uses RAM
        # TODO: async sessions would be a good idea to not block the current thread
        while True:
            try:
                async with asyncio.TaskGroup() as tg:
                    for queue in [q for q in self.queues.values() if not q.empty()]:
                        # sessions cannot be shared between coroutines, we need to create a new session for each coroutine
                        # https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks
                        transaction: Transaction = await queue.get()
                        with self.get_session() as session:

                            async def exec_transaction_with_session_handling():
                                await self.exec_transaction(
                                    transaction,
                                    TransactionsProcessor(session),
                                    ChainSnapshot(session),
                                    AccountsManager(session),
                                    lambda contract_address: contract_snapshot_factory(
                                        contract_address, session, transaction
                                    ),
                                )
                                session.commit()

                            tg.create_task(exec_transaction_with_session_handling())

            except Exception as e:
                print("Error running consensus", e)
                print(traceback.format_exc())
            await asyncio.sleep(DEFAULT_CONSENSUS_SLEEP_TIME)

    async def exec_transaction(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        snapshot: ChainSnapshot,
        accounts_manager: AccountsManager,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
        node_factory: Callable[
            [
                dict,
                ExecutionMode,
                ContractSnapshot,
                Receipt | None,
                MessageHandler,
                Callable[[str], ContractSnapshot],
            ],
            Node,
        ] = node_factory,
    ):
        msg_handler = self.msg_handler

        # Create initial state context
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            snapshot=snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=msg_handler,
        )

        # State transitions
        state = PendingState()
        while True:
            next_state = await state.handle(context)
            if next_state is None:
                break
            state = next_state

    @staticmethod
    def dispatch_transaction_status_update(
        transactions_processor: TransactionsProcessor,
        transaction_hash: str,
        new_status: TransactionStatus,
        msg_handler: MessageHandler,
    ):
        transactions_processor.update_transaction_status(transaction_hash, new_status)

        msg_handler.send_message(
            LogEvent(
                "transaction_status_updated",
                EventType.INFO,
                EventScope.CONSENSUS,
                f"{str(new_status.value)} {str(transaction_hash)}",
                {
                    "hash": str(transaction_hash),
                    "new_status": str(new_status.value),
                },
                transaction_hash=transaction_hash,
            )
        )

    @staticmethod
    def execute_transfer(
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        accounts_manager: AccountsManager,
        msg_handler: MessageHandler,
    ):
        """
        Executes a native token transfer between Externally Owned Accounts (EOAs).

        This function handles the transfer of native tokens from one EOA to another.
        It updates the balances of both the sender and recipient accounts, and
        manages the transaction status throughout the process.

        Args:
            transaction (dict): The transaction details including from_address, to_address, and value.
            transactions_processor (TransactionsProcessor): Processor to update transaction status.
            accounts_manager (AccountsManager): Manager to handle account balance updates.
        """

        # If from_address is None, it is a fund_account call
        if not transaction.from_address is None:
            # Get the balance of the sender account
            from_balance = accounts_manager.get_account_balance(
                transaction.from_address
            )

            # If the sender does not have enough balance, set the transaction status to UNDETERMINED
            if from_balance < transaction.value:
                ConsensusAlgorithm.dispatch_transaction_status_update(
                    transactions_processor,
                    transaction.hash,
                    TransactionStatus.UNDETERMINED,
                    msg_handler,
                )
                return

            # Update the balance of the sender account
            accounts_manager.update_account_balance(
                transaction.from_address, from_balance - transaction.value
            )

        # If to_address is None, it is a burn call
        if not transaction.to_address is None:
            to_balance = accounts_manager.get_account_balance(transaction.to_address)

            # Update the balance of the recipient account
            accounts_manager.update_account_balance(
                transaction.to_address, to_balance + transaction.value
            )

        ConsensusAlgorithm.dispatch_transaction_status_update(
            transactions_processor,
            transaction.hash,
            TransactionStatus.FINALIZED,
            msg_handler,
        )

    def run_appeal_window_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._appeal_window())
        loop.close()

    async def _appeal_window(self):
        FINALITY_WINDOW = int(os.getenv("FINALITY_WINDOW"))
        while True:
            with self.get_session() as session:
                chain_snapshot = ChainSnapshot(session)
                accepted_transactions = (
                    chain_snapshot.get_accepted_transactions()
                )  # TODO: also get undetermined transactions
                for transaction in accepted_transactions:
                    transaction = Transaction.from_dict(transaction)
                    if not transaction.appealed:
                        if (
                            int(time.time()) - transaction.timestamp_accepted
                        ) > FINALITY_WINDOW:
                            context = TransactionContext(
                                transaction=transaction,
                                transactions_processor=TransactionsProcessor(session),
                                snapshot=chain_snapshot,
                                accounts_manager=AccountsManager(session),
                                contract_snapshot_factory=lambda contract_address: contract_snapshot_factory(
                                    contract_address, session, transaction
                                ),
                                node_factory=node_factory,
                                msg_handler=self.msg_handler,
                            )
                            state = FinalizingState()
                            await state.handle(context)
                            session.commit()
                    else:
                        transactions_processor = TransactionsProcessor(session)
                        context = TransactionContext(
                            transaction=transaction,
                            transactions_processor=transactions_processor,
                            snapshot=chain_snapshot,
                            accounts_manager=AccountsManager(session),
                            contract_snapshot_factory=lambda contract_address: contract_snapshot_factory(
                                contract_address, session, transaction
                            ),
                            node_factory=node_factory,
                            msg_handler=self.msg_handler,
                        )
                        context.consensus_data.leader_receipt = (
                            transaction.consensus_data.leader_receipt
                        )
                        try:
                            context.remaining_validators = (
                                ConsensusAlgorithm.get_extra_validators(
                                    chain_snapshot, transaction.consensus_data
                                )
                            )
                        except ValueError as e:
                            print(e, transaction)
                            context.transactions_processor.set_transaction_appeal(
                                context.transaction.hash, False
                            )
                            context.transaction.appealed = False
                            session.commit()
                        else:
                            context.num_validators = len(
                                context.remaining_validators
                            )  # new amount added (N + 2)
                            context.votes = {}
                            context.contract_snapshot_supplier = (
                                lambda: context.contract_snapshot_factory(
                                    context.transaction.to_address
                                )
                            )

                            # State transitions
                            state = CommittingState()
                            while True:
                                next_state = await state.handle(context)
                                if next_state is None:
                                    break
                                state = next_state
                            session.commit()

            await asyncio.sleep(1)

    @staticmethod
    def get_extra_validators(snapshot: ChainSnapshot, consensus_data: ConsensusData):
        current_validators_addresses = {
            validator.node_config["address"] for validator in consensus_data.validators
        }
        current_validators_addresses.add(
            consensus_data.leader_receipt.node_config["address"]
        )
        not_used_validators = [
            validator
            for validator in snapshot.get_all_validators()
            if validator["address"] not in current_validators_addresses
        ]
        if len(not_used_validators) == 0:
            raise ValueError(
                "No validators found for appeal, waiting for next appeal request: "
            )
        return get_validators_for_transaction(
            not_used_validators, len(consensus_data.validators) + 1 + 2
        )  # plus one because of the leader, plus two because of the appeal

    @staticmethod
    def get_validators_from_consensus_data(
        all_validators: List[dict], consensus_data: ConsensusData
    ):
        current_validators_addresses = {
            validator.node_config["address"] for validator in consensus_data.validators
        }
        return [
            validator
            for validator in all_validators
            if validator["address"] in current_validators_addresses
        ]


class TransactionContext:
    def __init__(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        snapshot: ChainSnapshot,
        accounts_manager: AccountsManager,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
        node_factory: Callable[
            [
                dict,
                ExecutionMode,
                ContractSnapshot,
                Receipt | None,
                MessageHandler,
                Callable[[str], ContractSnapshot],
            ],
            Node,
        ],
        msg_handler: MessageHandler,
    ):
        self.transaction = transaction
        self.transactions_processor = transactions_processor
        self.snapshot = snapshot
        self.accounts_manager = accounts_manager
        self.contract_snapshot_factory = contract_snapshot_factory
        self.node_factory = node_factory
        self.msg_handler = msg_handler
        self.consensus_data = ConsensusData(
            votes={}, leader_receipt=None, validators=[]
        )
        self.iterator_rotation: Iterator[list] | None = None
        self.remaining_validators: list = []
        self.num_validators: int = 0
        self.contract_snapshot_supplier: Callable[[], ContractSnapshot] | None = None
        self.votes: dict = {}
        self.validator_nodes: list = []
        self.validation_results: list = []


class TransactionState(ABC):
    @abstractmethod
    async def handle(self, context: TransactionContext):
        pass


class PendingState(TransactionState):
    async def handle(self, context):
        if (
            context.transactions_processor.get_transaction_by_hash(
                context.transaction.hash
            )["status"]
            != TransactionStatus.PENDING.value
        ):
            # This is a patch for a TOCTOU problem we have https://github.com/yeagerai/genlayer-simulator/issues/387
            # Problem: Pending transactions are checked by `_crawl_snapshot`, which appends them to queues. These queues are consumed by `_run_consensus`, which processes the transactions. This means that a transaction can be processed multiple times, since `_crawl_snapshot` can append the same transaction to the queue multiple times.
            # Partial solution: This patch checks if the transaction is still pending before processing it. This is not the best solution, but we'll probably refactor the whole consensus algorithm in the short term.
            print(" ~ ~ ~ ~ ~ TRANSACTION ALREADY IN PROCESS: ", context.transaction)
            return None

        print(" ~ ~ ~ ~ ~ EXECUTING TRANSACTION: ", context.transaction)

        # If transaction is a transfer, execute it
        # TODO: consider when the transfer involves a contract account, bridging, etc.
        if context.transaction.type == TransactionType.SEND:
            ConsensusAlgorithm.execute_transfer(
                context.transaction,
                context.transactions_processor,
                context.accounts_manager,
                context.msg_handler,
            )
            return None

        all_validators = context.snapshot.get_all_validators()
        if not all_validators:
            print(
                "No validators found for transaction, waiting for next round: ",
                context.transaction,
            )
            return None

        if context.transaction.appealed:
            # Generate a new leader and remove the old leader
            involved_validators = ConsensusAlgorithm.get_validators_from_consensus_data(
                all_validators, context.transaction.consensus_data
            )
            context.transactions_processor.set_transaction_appeal(
                context.transaction.hash, False
            )
            context.transaction.appealed = False
        else:
            involved_validators = get_validators_for_transaction(
                all_validators, DEFAULT_VALIDATORS_COUNT
            )

        context.iterator_rotation = rotate(involved_validators)

        return ProposingState()


class ProposingState(TransactionState):
    async def handle(self, context):
        # Select leader
        try:
            validators = next(context.iterator_rotation)
        except StopIteration:
            # All rotations are done, no consensus reached
            return UndeterminedState()

        [leader, *remaining_validators] = validators

        if context.transaction.leader_only:
            remaining_validators = []

        contract_snapshot_supplier = lambda: context.contract_snapshot_factory(
            context.transaction.to_address
        )

        leader_node = context.node_factory(
            leader,
            ExecutionMode.LEADER,
            contract_snapshot_supplier(),
            None,
            context.msg_handler,
            context.contract_snapshot_factory,
        )

        # Get leader receipt
        leader_receipt = await leader_node.exec_transaction(context.transaction)
        votes = {leader["address"]: leader_receipt.vote.value}

        context.consensus_data.votes = votes
        context.consensus_data.leader_receipt = leader_receipt
        context.consensus_data.validators = []
        context.transactions_processor.set_transaction_result(
            context.transaction.hash, context.consensus_data.to_dict()
        )

        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.PROPOSING,
            context.msg_handler,
        )
        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        context.remaining_validators = remaining_validators
        context.num_validators = len(remaining_validators) + 1
        context.contract_snapshot_supplier = contract_snapshot_supplier
        context.votes = votes

        return CommittingState()


class CommittingState(TransactionState):
    async def handle(self, context):
        # Create the validator nodes
        context.validator_nodes = [
            context.node_factory(
                validator,
                ExecutionMode.VALIDATOR,
                context.contract_snapshot_supplier(),
                context.consensus_data.leader_receipt,
                context.msg_handler,
                context.contract_snapshot_factory,
            )
            for validator in context.remaining_validators
        ]

        # Get validator receipts
        validation_tasks = [
            validator.exec_transaction(context.transaction)
            for validator in context.validator_nodes
        ]
        context.validation_results = await asyncio.gather(*validation_tasks)

        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.COMMITTING,
            context.msg_handler,
        )
        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        return RevealingState()


class RevealingState(TransactionState):
    async def handle(self, context):
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.REVEALING,
            context.msg_handler,
        )

        for i, validation_result in enumerate(context.validation_results):
            context.votes[context.validator_nodes[i].address] = (
                validation_result.vote.value
            )
            single_reveal_votes = {
                context.consensus_data.leader_receipt.node_config[
                    "address"
                ]: context.consensus_data.leader_receipt.vote.value,
                context.validator_nodes[i].address: validation_result.vote.value,
            }
            context.consensus_data.votes = single_reveal_votes
            context.consensus_data.validators = [validation_result]
            context.transactions_processor.set_transaction_result(
                context.transaction.hash, context.consensus_data.to_dict()
            )
            context.transactions_processor.create_rollup_transaction(
                context.transaction.hash
            )

        if (
            len([vote for vote in context.votes.values() if vote == Vote.AGREE.value])
            > context.num_validators // 2
        ):
            if context.transaction.appealed:
                # Appeal failed
                context.votes.update(context.transaction.consensus_data.votes)
                context.validation_results = (
                    context.transaction.consensus_data.validators
                    + context.validation_results
                )

            return AcceptedState()
        else:
            if context.transaction.appealed:
                # Appeal succeeded
                context.consensus_data.votes = (
                    context.transaction.consensus_data.votes | context.votes
                )
                context.consensus_data.validators = (
                    context.transaction.consensus_data.validators
                    + context.validation_results
                )
                context.transactions_processor.set_transaction_result(
                    context.transaction.hash, context.consensus_data.to_dict()
                )
                ConsensusAlgorithm.dispatch_transaction_status_update(
                    context.transactions_processor,
                    context.transaction.hash,
                    TransactionStatus.PENDING,
                    context.msg_handler,
                )
                context.transactions_processor.create_rollup_transaction(
                    context.transaction.hash
                )
                # TODO: put all the transactions that came after this one back in the pending queue
                return None  # Transaction will be picked up by _crawl_snapshot
            else:
                print(
                    "Consensus not reached for transaction, rotating leader: ",
                    context.transaction,
                )
                context.consensus_data.votes = context.votes
                context.consensus_data.validators = context.validation_results
                return ProposingState()


class AcceptedState(TransactionState):
    async def handle(self, context):
        if not context.transaction.appealed:
            # When appeal fails, the appeal window is not reset
            context.transactions_processor.set_transaction_timestamp_accepted(
                context.transaction.hash
            )
        context.transactions_processor.set_transaction_appeal(
            context.transaction.hash, False
        )
        context.transaction.appealed = False

        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.ACCEPTED,
            context.msg_handler,
        )

        context.consensus_data.votes = context.votes
        context.consensus_data.validators = context.validation_results
        context.transactions_processor.set_transaction_result(
            context.transaction.hash, context.consensus_data.to_dict()
        )
        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        context.msg_handler.send_message(
            LogEvent(
                "consensus_reached",
                EventType.SUCCESS,
                EventScope.CONSENSUS,
                "Reached consensus",
                context.consensus_data.to_dict(),
                transaction_hash=context.transaction.hash,
            )
        )
        return None


class UndeterminedState(TransactionState):
    async def handle(self, context):
        print("Consensus not reached for transaction: ", context.transaction)
        context.msg_handler.send_message(
            LogEvent(
                "consensus_failed",
                EventType.ERROR,
                EventScope.CONSENSUS,
                "Failed to reach consensus",
                transaction_hash=context.transaction.hash,
            )
        )
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.UNDETERMINED,
            context.msg_handler,
        )
        context.transactions_processor.set_transaction_result(
            context.transaction.hash,
            context.consensus_data.to_dict(),
        )
        return None


class FinalizingState(TransactionState):
    async def handle(self, context):
        leader_receipt = context.transaction.consensus_data.leader_receipt
        contract_snapshot_supplier = lambda: context.contract_snapshot_factory(
            context.transaction.to_address
        )
        leaders_contract_snapshot = contract_snapshot_supplier()

        if leader_receipt.execution_result == ExecutionResultStatus.SUCCESS:
            # Register contract if it is a new contract
            if context.transaction.type == TransactionType.DEPLOY_CONTRACT:
                new_contract = {
                    "id": context.transaction.data["contract_address"],
                    "data": {
                        "state": leader_receipt.contract_state,
                        "code": context.transaction.data["contract_code"],
                    },
                }
                leaders_contract_snapshot.register_contract(new_contract)

                context.msg_handler.send_message(
                    LogEvent(
                        "deployed_contract",
                        EventType.SUCCESS,
                        EventScope.GENVM,
                        "Contract deployed",
                        new_contract,
                        transaction_hash=context.transaction.hash,
                    )
                )
            # Update contract state if it is an existing contract
            else:
                leaders_contract_snapshot.update_contract_state(
                    leader_receipt.contract_state
                )

        # Finalize transaction
        context.transactions_processor.set_transaction_result(
            context.transaction.hash,
            context.transaction.consensus_data.to_dict(),
        )
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.FINALIZED,
            context.msg_handler,
        )
        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        # Insert pending transactions generated by contract-to-contract calls
        pending_transactions = leader_receipt.pending_transactions
        for pending_transaction in pending_transactions:
            nonce = context.transactions_processor.get_transaction_count(
                context.transaction.to_address
            )
            context.transactions_processor.insert_transaction(
                context.transaction.to_address,  # new calls are done by the contract
                pending_transaction.address,
                {
                    "calldata": pending_transaction.calldata,
                },
                value=0,  # we only handle EOA transfers at the moment, so no value gets transferred
                type=TransactionType.RUN_CONTRACT.value,
                nonce=nonce,
                leader_only=context.transaction.leader_only,  # Cascade
                triggered_by_hash=context.transaction.hash,
            )


def rotate(nodes: list) -> Iterator[list]:
    nodes = deque(nodes)
    for _ in range(len(nodes)):
        yield list(nodes)
        nodes.rotate(-1)
