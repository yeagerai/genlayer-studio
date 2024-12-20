from collections import defaultdict
from typing import Callable
from unittest.mock import AsyncMock, Mock
import time
import threading
import asyncio
import pytest
from backend.consensus.base import (
    ConsensusAlgorithm,
    PendingState,
    CommittingState,
    FinalizingState,
    TransactionContext,
)
from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.models import TransactionStatus
from backend.domain.types import Transaction, TransactionType
from backend.node.base import Node
from backend.node.types import ExecutionMode, ExecutionResultStatus, Receipt, Vote
from backend.protocol_rpc.message_handler.base import MessageHandler

DEFAULT_FINALITY_WINDOW = 5
DEFAULT_EXEC_RESULT = b"\x00\x00"  # success(null)


class AccountsManagerMock:
    def __init__(self, accounts: dict[str, int] | None = None):
        self.accounts = accounts or defaultdict(int)

    def get_account_balance(self, address: str) -> int:
        return self.accounts[address]

    def update_account_balance(self, address: str, balance: int):
        self.accounts[address] = balance


class TransactionsProcessorMock:
    def __init__(self, transactions=None):
        self.transactions = transactions or []
        self.updated_transaction_status_history = defaultdict(list)

    def get_transaction_by_hash(self, transaction_hash: str) -> dict:
        for transaction in self.transactions:
            if transaction["hash"] == transaction_hash:
                return transaction
        raise ValueError(f"Transaction with hash {transaction_hash} not found")

    def update_transaction_status(
        self, transaction_hash: str, status: TransactionStatus
    ):
        self.get_transaction_by_hash(transaction_hash)["status"] = status.value
        self.updated_transaction_status_history[transaction_hash].append(status)

    def set_transaction_result(self, transaction_hash: str, consensus_data: dict):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["consensus_data"] = consensus_data

    def set_transaction_appeal(self, transaction_hash: str, appeal: bool):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appealed"] = appeal

    def set_transaction_timestamp_awaiting_finalization(
        self, transaction_hash: str, timestamp_awaiting_finalization: int = None
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)
        if timestamp_awaiting_finalization:
            transaction["timestamp_awaiting_finalization"] = (
                timestamp_awaiting_finalization
            )
        else:
            transaction["timestamp_awaiting_finalization"] = int(time.time())

    def get_accepted_undetermined_transactions(self):
        result = []
        for transaction in self.transactions:
            if (transaction["status"] == TransactionStatus.ACCEPTED.value) or (
                transaction["status"] == TransactionStatus.UNDETERMINED.value
            ):
                result.append(transaction)
        return sorted(result, key=lambda x: x["timestamp_awaiting_finalization"])

    def create_rollup_transaction(self, transaction_hash: str):
        pass

    def set_transaction_appeal_failed(self, transaction_hash: str, appeal_failed: int):
        if appeal_failed < 0:
            raise ValueError("appeal_failed must be a non-negative integer")
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_failed"] = appeal_failed

    def set_transaction_appeal_undetermined(
        self, transaction_hash: str, appeal_undetermined: bool
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_undetermined"] = appeal_undetermined

    def get_newer_transactions(self, transaction_hash: str):
        return []


class SnapshotMock:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_all_validators(self):
        return self.nodes


def transaction_to_dict(transaction: Transaction) -> dict:
    return {
        "hash": transaction.hash,
        "status": transaction.status.value,
        "from_address": transaction.from_address,
        "to_address": transaction.to_address,
        "input_data": transaction.input_data,
        "data": transaction.data,
        "consensus_data": transaction.consensus_data,
        "nonce": transaction.nonce,
        "value": transaction.value,
        "type": transaction.type.value,
        "gaslimit": transaction.gaslimit,
        "r": transaction.r,
        "s": transaction.s,
        "v": transaction.v,
        "leader_only": transaction.leader_only,
        "created_at": transaction.created_at,
        "ghost_contract_address": transaction.ghost_contract_address,
        "appealed": transaction.appealed,
        "timestamp_awaiting_finalization": transaction.timestamp_awaiting_finalization,
        "appeal_failed": transaction.appeal_failed,
        "appeal_undetermined": transaction.appeal_undetermined,
    }


def contract_snapshot_factory(address: str):
    class ContractSnapshotMock:
        def __init__(self):
            self.address = address

        def update_contract_state(self, state: dict[str, str]):
            pass

    return ContractSnapshotMock()


def init_dummy_transaction():
    return Transaction(
        hash="transaction_hash",
        from_address="from_address",
        to_address="to_address",
        status=TransactionStatus.PENDING,
        type=TransactionType.RUN_CONTRACT,
    )


def get_nodes_specs(number_of_nodes: int):
    return [
        {
            "address": f"address{i}",
            "stake": i + 1,
            "provider": f"provider{i}",
            "model": f"model{i}",
            "config": f"config{i}",
        }
        for i in range(number_of_nodes)
    ]


async def _appeal_window(
    stop_event: threading.Event,
    transactions_processor: TransactionsProcessorMock,
    msg_handler: MessageHandler,
    nodes: list[dict],
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
):
    while not stop_event.is_set():
        accepted_undetermined_transactions = (
            transactions_processor.get_accepted_undetermined_transactions()
        )
        for i, transaction in enumerate(accepted_undetermined_transactions):
            transaction = Transaction.from_dict(transaction)
            if not transaction.appealed:
                if (transaction.leader_only) or (
                    (int(time.time()) - transaction.timestamp_awaiting_finalization)
                    > DEFAULT_FINALITY_WINDOW
                ):
                    if i == 0:
                        finalize_current_transaction = True
                    else:
                        previous_transaction_hash = accepted_undetermined_transactions[
                            i - 1
                        ]["hash"]
                        previous_transaction = Transaction.from_dict(
                            transactions_processor.get_transaction_by_hash(
                                previous_transaction_hash
                            )
                        )
                        if previous_transaction.status == TransactionStatus.FINALIZED:
                            finalize_current_transaction = True
                        else:
                            finalize_current_transaction = False

                    if finalize_current_transaction:
                        context = TransactionContext(
                            transaction=transaction,
                            transactions_processor=transactions_processor,
                            snapshot=SnapshotMock(nodes),
                            accounts_manager=AccountsManagerMock(),
                            contract_snapshot_factory=contract_snapshot_factory,
                            node_factory=node_factory,
                            msg_handler=msg_handler,
                        )
                        state = FinalizingState()
                        await state.handle(context)

            else:
                # Handle transactions that are appealed
                if transaction.status == TransactionStatus.UNDETERMINED:
                    # Leader appeal
                    # Appeal data member is used in the frontend for both types of appeals
                    # Here the type is refined based on the status
                    transactions_processor.set_transaction_appeal_undetermined(
                        transaction.hash, True
                    )
                    transactions_processor.set_transaction_appeal(
                        transaction.hash, False
                    )
                    transaction.appeal_undetermined = True
                    transaction.appealed = False

                    ConsensusAlgorithm.dispatch_transaction_status_update(
                        transactions_processor,
                        transaction.hash,
                        TransactionStatus.PENDING,
                        msg_handler,
                    )

                    # Create a transaction context for the appeal process
                    context = TransactionContext(
                        transaction=transaction,
                        transactions_processor=transactions_processor,
                        snapshot=SnapshotMock(nodes),
                        accounts_manager=AccountsManagerMock(),
                        contract_snapshot_factory=contract_snapshot_factory,
                        node_factory=node_factory,
                        msg_handler=msg_handler,
                    )

                    # Begin state transitions starting from PendingState
                    state = PendingState(called_from_pending_queue=False)
                    while True:
                        next_state = await state.handle(context)
                        if next_state is None:
                            break
                        elif next_state == "leader_appeal_success":
                            rollback_transactions(context)
                            break
                        state = next_state

                else:
                    chain_snapshot = SnapshotMock(nodes)
                    context = TransactionContext(
                        transaction=transaction,
                        transactions_processor=transactions_processor,
                        snapshot=chain_snapshot,
                        accounts_manager=AccountsManagerMock(),
                        contract_snapshot_factory=contract_snapshot_factory,
                        node_factory=node_factory,
                        msg_handler=msg_handler,
                    )
                    context.consensus_data.leader_receipt = (
                        transaction.consensus_data.leader_receipt
                    )
                    nb_current_validators = (
                        len(transaction.consensus_data.validators) + 1
                    )
                    current_validators_addresses = {
                        validator.node_config["address"]
                        for validator in transaction.consensus_data.validators
                    }
                    current_validators_addresses.add(
                        transaction.consensus_data.leader_receipt.node_config["address"]
                    )
                    try:
                        context.remaining_validators = (
                            ConsensusAlgorithm.get_extra_validators(
                                chain_snapshot,
                                transaction.consensus_data,
                                transaction.appeal_failed,
                            )
                        )
                    except ValueError as e:
                        print(e, transaction)
                        context.transactions_processor.set_transaction_appeal(
                            context.transaction.hash, False
                        )
                        context.transaction.appealed = False
                    else:
                        if transaction.appeal_failed == 0:
                            n = nb_current_validators
                            nb_validators_processing_appeal = n + 2
                        elif transaction.appeal_failed == 1:
                            n = (nb_current_validators - 2) // 2
                            nb_validators_processing_appeal = 2 * n + 3
                        else:
                            n = (nb_current_validators - 3) // (
                                2 * transaction.appeal_failed - 1
                            )
                            nb_validators_processing_appeal = 4 * n + 3

                        context.num_validators = len(context.remaining_validators)
                        assert context.num_validators == nb_validators_processing_appeal

                        context.votes = {}
                        context.contract_snapshot_supplier = (
                            lambda: context.contract_snapshot_factory(
                                context.transaction.to_address
                            )
                        )

                        new_validators_addresses = {
                            validator["address"]
                            for validator in context.remaining_validators
                        }
                        assert new_validators_addresses != current_validators_addresses

                        # State transitions
                        state = CommittingState()
                        while True:
                            next_state = await state.handle(context)
                            if next_state is None:
                                break
                            elif next_state == "validator_appeal_success":
                                rollback_transactions(context)
                                ConsensusAlgorithm.dispatch_transaction_status_update(
                                    context.transactions_processor,
                                    context.transaction.hash,
                                    TransactionStatus.PENDING,
                                    context.msg_handler,
                                )

                                # Transaction will be picked up by _crawl_snapshot
                                break
                            assert (
                                len(context.validator_nodes)
                                == nb_validators_processing_appeal
                            )
                            state = next_state

        await asyncio.sleep(1)


def rollback_transactions(context: TransactionContext):
    """
    Rollback newer transactions.
    """
    # Set all transactions with higher created_at to PENDING
    future_transactions = context.transactions_processor.get_newer_transactions(
        context.transaction.hash
    )
    for future_transaction in future_transactions:
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            future_transaction["hash"],
            TransactionStatus.PENDING,
            context.msg_handler,
        )


def run_async_task_in_thread(
    stop_event: threading.Event,
    transactions_processor: TransactionsProcessorMock,
    msg_handler: MessageHandler,
    nodes: list[dict],
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
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _appeal_window(
                stop_event, transactions_processor, msg_handler, nodes, node_factory
            )
        )
    finally:
        loop.close()


@pytest.fixture
def managed_thread(request):
    def start_thread(
        transactions_processor: TransactionsProcessorMock,
        msg_handler: MessageHandler,
        nodes: list[dict],
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
    ):
        stop_event = threading.Event()
        thread = threading.Thread(
            target=run_async_task_in_thread,
            args=(stop_event, transactions_processor, msg_handler, nodes, node_factory),
        )
        thread.start()

        def fin():
            stop_event.set()
            thread.join()

        request.addfinalizer(fin)

        return thread

    return start_thread


def node_factory(
    node: dict,
    mode: ExecutionMode,
    contract_snapshot: ContractSnapshot,
    receipt: Receipt | None,
    msg_handler: MessageHandler,
    contract_snapshot_factory: Callable[[str], ContractSnapshot],
    vote: Vote,
):
    mock = Mock(Node)

    mock.validator_mode = mode
    mock.address = node["address"]
    mock.leader_receipt = receipt

    mock.exec_transaction = AsyncMock(
        return_value=Receipt(
            vote=vote,
            calldata=b"",
            mode=mode,
            gas_used=0,
            contract_state={},
            result=DEFAULT_EXEC_RESULT,
            node_config={"address": node["address"]},
            eq_outputs={},
            execution_result=ExecutionResultStatus.SUCCESS,
        )
    )

    return mock


def appeal(transaction: Transaction, transactions_processor: TransactionsProcessor):
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == False
    )
    transactions_processor.set_transaction_appeal(transaction.hash, True)
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == True
    )


def check_validator_count(
    transaction: Transaction, transactions_processor: TransactionsProcessor, n: int
):
    assert (
        len(
            transactions_processor.get_transaction_by_hash(transaction.hash)[
                "consensus_data"
            ]["validators"]
        )
        == n - 1  # -1 because of the leader
    )


def get_leader_address(
    transaction: Transaction, transactions_processor: TransactionsProcessor
):
    transaction_dict = transactions_processor.get_transaction_by_hash(transaction.hash)
    return transaction_dict["consensus_data"]["leader_receipt"]["node_config"][
        "address"
    ]


def get_validator_addresses(
    transaction: Transaction, transactions_processor: TransactionsProcessor
):
    transaction_dict = transactions_processor.get_transaction_by_hash(transaction.hash)
    return {
        validator["node_config"]["address"]
        for validator in transaction_dict["consensus_data"]["validators"]
    }
