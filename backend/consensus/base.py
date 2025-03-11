# backend/consensus/base.py

DEFAULT_VALIDATORS_COUNT = 5
DEFAULT_CONSENSUS_SLEEP_TIME = 5

import os
import asyncio
import traceback
from typing import Callable, Iterator, List, Iterable, Literal
import time
from abc import ABC, abstractmethod
import threading
import random

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
from backend.node.types import (
    ExecutionMode,
    Receipt,
    Vote,
    ExecutionResultStatus,
    PendingTransaction,
)
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
    """
    Factory function to create a Node instance.

    Args:
        validator (dict): Validator information.
        validator_mode (ExecutionMode): Mode of execution for the validator.
        contract_snapshot (ContractSnapshot): Snapshot of the contract state.
        leader_receipt (Receipt | None): Receipt of the leader node.
        msg_handler (MessageHandler): Handler for messaging.
        contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.

    Returns:
        Node: A new Node instance.
    """
    # Create a node instance with the provided parameters
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
    """
    Factory function to create a ContractSnapshot instance.

    Args:
        contract_address (str): The address of the contract.
        session (Session): The database session.
        transaction (Transaction): The transaction related to the contract.

    Returns:
        ContractSnapshot: A new ContractSnapshot instance.
    """
    # Check if the transaction is a contract deployment and the contract address matches the transaction's to address
    if (
        transaction.type == TransactionType.DEPLOY_CONTRACT
        and contract_address == transaction.to_address
        and transaction.status != TransactionStatus.ACCEPTED
    ):
        # Create a new ContractSnapshot instance for the new contract
        ret = ContractSnapshot(None, session)
        ret.contract_address = transaction.to_address
        ret.contract_code = transaction.data["contract_code"]
        ret.balance = transaction.value or 0
        ret.states = {"accepted": {}, "finalized": {}}
        ret.encoded_state = ret.states["accepted"]
        ret.ghost_contract_address = transaction.ghost_contract_address
        return ret

    # Return a ContractSnapshot instance for an existing contract
    return ContractSnapshot(contract_address, session)


def chain_snapshot_factory(session: Session):
    """
    Factory function to create a ChainSnapshot instance.

    Args:
        session (Session): The database session.

    Returns:
        ChainSnapshot: A new ChainSnapshot instance.
    """
    return ChainSnapshot(session)


def transactions_processor_factory(session: Session):
    """
    Factory function to create a TransactionsProcessor instance.

    Args:
        session (Session): The database session.

    Returns:
        TransactionsProcessor: A new TransactionsProcessor instance.
    """
    return TransactionsProcessor(session)


def accounts_manager_factory(session: Session):
    """
    Factory function to create an AccountsManager instance.

    Args:
        session (Session): The database session.

    Returns:
        AccountsManager: A new AccountsManager instance.
    """
    return AccountsManager(session)


class TransactionContext:
    """
    Class representing the context of a transaction.

    Attributes:
        transaction (Transaction): The transaction.
        transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
        chain_snapshot (ChainSnapshot): Snapshot of the chain state.
        accounts_manager (AccountsManager): Manager for accounts.
        contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
        node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        msg_handler (MessageHandler): Handler for messaging.
        consensus_data (ConsensusData): Data related to the consensus process.
        iterator_rotation (Iterator[list] | None): Iterator for rotating validators.
        remaining_validators (list): List of remaining validators.
        num_validators (int): Number of validators.
        contract_snapshot (ContractSnapshot | None): Snapshot of the contract state.
        votes (dict): Dictionary of votes.
        validator_nodes (list): List of validator nodes.
        validation_results (list): List of validation results.
    """

    def __init__(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
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
        """
        Initialize the TransactionContext.

        Args:
            transaction (Transaction): The transaction.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
            msg_handler (MessageHandler): Handler for messaging.
        """
        self.transaction = transaction
        self.transactions_processor = transactions_processor
        self.chain_snapshot = chain_snapshot
        self.accounts_manager = accounts_manager
        self.contract_snapshot_factory = contract_snapshot_factory
        self.node_factory = node_factory
        self.msg_handler = msg_handler
        self.consensus_data = ConsensusData(
            votes={}, leader_receipt=None, validators=[]
        )
        self.involved_validators: list[dict] = []
        self.remaining_validators: list = []
        self.num_validators: int = 0
        self.contract_snapshot_supplier: Callable[[], ContractSnapshot] | None = None
        self.votes: dict = {}
        self.validator_nodes: list = []
        self.validation_results: list = []
        self.rotation_count: int = 0


class ConsensusAlgorithm:
    """
    Class representing the consensus algorithm.

    Attributes:
        get_session (Callable[[], Session]): Function to get a database session.
        msg_handler (MessageHandler): Handler for messaging.
        pending_queues (dict[str, asyncio.Queue]): Dictionary of pending_queues for transactions.
        finality_window_time (int): Time in seconds for the finality window.
        consensus_sleep_time (int): Time in seconds for the consensus sleep time.
    """

    def __init__(
        self,
        get_session: Callable[[], Session],
        msg_handler: MessageHandler,
    ):
        """
        Initialize the ConsensusAlgorithm.

        Args:
            get_session (Callable[[], Session]): Function to get a database session.
            msg_handler (MessageHandler): Handler for messaging.
        """
        self.get_session = get_session
        self.msg_handler = msg_handler
        self.pending_queues: dict[str, asyncio.Queue] = {}
        self.finality_window_time = int(os.getenv("VITE_FINALITY_WINDOW"))
        self.consensus_sleep_time = DEFAULT_CONSENSUS_SLEEP_TIME
        self.pending_queue_stop_events: dict[str, asyncio.Event] = (
            {}
        )  # Events to stop tasks for each pending queue
        self.pending_queue_task_running: dict[str, bool] = (
            {}
        )  # Track running state for each pending queue

    def run_crawl_snapshot_loop(
        self,
        chain_snapshot_factory: Callable[
            [Session], ChainSnapshot
        ] = chain_snapshot_factory,
        transactions_processor_factory: Callable[
            [Session], TransactionsProcessor
        ] = transactions_processor_factory,
        stop_event: threading.Event = threading.Event(),
    ):
        """
        Run the loop to crawl snapshots.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            stop_event (threading.Event): Control signal to terminate the loop.
        """
        # Create a new event loop for crawling snapshots
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            self._crawl_snapshot(
                chain_snapshot_factory, transactions_processor_factory, stop_event
            )
        )
        loop.close()

    async def _crawl_snapshot(
        self,
        chain_snapshot_factory: Callable[[Session], ChainSnapshot],
        transactions_processor_factory: Callable[[Session], TransactionsProcessor],
        stop_event: threading.Event,
    ):
        """
        Crawl snapshots and process pending transactions.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            stop_event (threading.Event): Control signal to terminate the loop.
        """
        while not stop_event.is_set():
            with self.get_session() as session:
                chain_snapshot = chain_snapshot_factory(session)
                transactions_processor = transactions_processor_factory(session)
                pending_transactions = chain_snapshot.get_pending_transactions()
                for transaction in pending_transactions:
                    transaction = Transaction.from_dict(transaction)
                    address = transaction.to_address

                    # Initialize queue and stop event for the address if not present
                    if address not in self.pending_queues:
                        self.pending_queues[address] = asyncio.Queue()

                    if address not in self.pending_queue_stop_events:
                        self.pending_queue_stop_events[address] = asyncio.Event()

                    # Only add to the queue if the stop event is not set
                    if not self.pending_queue_stop_events[address].is_set():
                        await self.pending_queues[address].put(transaction)

                        # Set the transaction as activated so it is not added to the queue again
                        ConsensusAlgorithm.dispatch_transaction_status_update(
                            transactions_processor,
                            transaction.hash,
                            TransactionStatus.ACTIVATED,
                            self.msg_handler,
                        )

            await asyncio.sleep(self.consensus_sleep_time)

    def run_process_pending_transactions_loop(
        self,
        chain_snapshot_factory: Callable[
            [Session], ChainSnapshot
        ] = chain_snapshot_factory,
        transactions_processor_factory: Callable[
            [Session], TransactionsProcessor
        ] = transactions_processor_factory,
        accounts_manager_factory: Callable[
            [Session], AccountsManager
        ] = accounts_manager_factory,
        contract_snapshot_factory: Callable[
            [str, Session, Transaction], ContractSnapshot
        ] = contract_snapshot_factory,
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
        stop_event: threading.Event = threading.Event(),
    ):
        """
        Run the process pending transactions loop.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            accounts_manager_factory (Callable[[Session], AccountsManager]): Creates managers to handle account state.
            contract_snapshot_factory (Callable[[str, Session, Transaction], ContractSnapshot]): Creates snapshots of contract states.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Creates node instances that can execute contracts and process transactions.
            stop_event (threading.Event): Control signal to terminate the pending transactions process.
        """
        # Create a new event loop for running the processing of pending transactions
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            self._process_pending_transactions(
                chain_snapshot_factory,
                transactions_processor_factory,
                accounts_manager_factory,
                contract_snapshot_factory,
                node_factory,
                stop_event,
            )
        )
        loop.close()

    async def _process_pending_transactions(
        self,
        chain_snapshot_factory: Callable[[Session], ChainSnapshot],
        transactions_processor_factory: Callable[[Session], TransactionsProcessor],
        accounts_manager_factory: Callable[[Session], AccountsManager],
        contract_snapshot_factory: Callable[
            [str, Session, Transaction], ContractSnapshot
        ],
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
        stop_event: threading.Event,
    ):
        """
        Process pending transactions.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            accounts_manager_factory (Callable[[Session], AccountsManager]): Creates managers to handle account state.
            contract_snapshot_factory (Callable[[str, Session, Transaction], ContractSnapshot]): Creates snapshots of contract states.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Creates node instances that can execute contracts and process transactions.
            stop_event (threading.Event): Control signal to terminate the pending transactions process.
        """
        # Set a new event loop for the processing of pending transactions
        asyncio.set_event_loop(asyncio.new_event_loop())
        # Note: ollama uses GPU resources and webrequest aka selenium uses RAM
        # TODO: Consider using async sessions to avoid blocking the current thread
        while not stop_event.is_set():
            try:
                async with asyncio.TaskGroup() as tg:
                    for queue_address, queue in self.pending_queues.items():
                        if (
                            not queue.empty()
                            and not self.pending_queue_stop_events.get(
                                queue_address, asyncio.Event()
                            ).is_set()
                        ):
                            # Sessions cannot be shared between coroutines; create a new session for each coroutine
                            # Reference: https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks
                            self.pending_queue_task_running[queue_address] = True
                            transaction: Transaction = await queue.get()
                            with self.get_session() as session:

                                async def exec_transaction_with_session_handling(
                                    session: Session,
                                    transaction: Transaction,
                                    queue_address: str,
                                ):
                                    transactions_processor = (
                                        transactions_processor_factory(session)
                                    )
                                    await self.exec_transaction(
                                        transaction,
                                        transactions_processor,
                                        chain_snapshot_factory(session),
                                        accounts_manager_factory(session),
                                        lambda contract_address: contract_snapshot_factory(
                                            contract_address, session, transaction
                                        ),
                                        node_factory,
                                    )
                                    session.commit()
                                    self.pending_queue_task_running[queue_address] = (
                                        False
                                    )

                            tg.create_task(
                                exec_transaction_with_session_handling(
                                    session, transaction, queue_address
                                )
                            )

            except Exception as e:
                print("Error running consensus", e)
                print(traceback.format_exc())
            finally:
                for queue_address in self.pending_queues:
                    self.pending_queue_task_running[queue_address] = False
            await asyncio.sleep(self.consensus_sleep_time)

    def is_pending_queue_task_running(self, address: str):
        """
        Check if a task for a specific pending queue is currently running.
        """
        return self.pending_queue_task_running.get(address, False)

    def stop_pending_queue_task(self, address: str):
        """
        Signal the task for a specific pending queue to stop.
        """
        if address in self.pending_queues:
            if address not in self.pending_queue_stop_events:
                self.pending_queue_stop_events[address] = asyncio.Event()
            self.pending_queue_stop_events[address].set()

    def start_pending_queue_task(self, address: str):
        """
        Allow the task for a specific pending queue to start.
        """
        if address in self.pending_queue_stop_events:
            self.pending_queue_stop_events[address].clear()

    async def exec_transaction(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
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
    ):
        """
        Execute a transaction.

        Args:
            transaction (Transaction): The transaction to execute.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        """
        # Create initial state context for the transaction
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=self.msg_handler,
        )

        # Begin state transitions starting from PendingState
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
        """
        Dispatch a transaction status update.

        Args:
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            transaction_hash (str): Hash of the transaction.
            new_status (TransactionStatus): New status of the transaction.
            msg_handler (MessageHandler): Handler for messaging.
        """
        # Update the transaction status in the transactions processor
        transactions_processor.update_transaction_status(transaction_hash, new_status)

        # Send a message indicating the transaction status update
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
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            accounts_manager (AccountsManager): Manager to handle account balance updates.
        """

        # Check if the transaction is a fund_account call
        if not transaction.from_address is None:
            # Get the balance of the sender account
            from_balance = accounts_manager.get_account_balance(
                transaction.from_address
            )

            # Check if the sender has enough balance
            if from_balance < transaction.value:
                # Set the transaction status to UNDETERMINED if balance is insufficient
                ConsensusAlgorithm.dispatch_transaction_status_update(
                    transactions_processor,
                    transaction.hash,
                    TransactionStatus.UNDETERMINED,
                    msg_handler,
                )

                transactions_processor.create_rollup_transaction(transaction.hash)
                return

            # Update the balance of the sender account
            accounts_manager.update_account_balance(
                transaction.from_address, from_balance - transaction.value
            )

        # Check if the transaction is a burn call
        if not transaction.to_address is None:
            # Get the balance of the recipient account
            to_balance = accounts_manager.get_account_balance(transaction.to_address)

            # Update the balance of the recipient account
            accounts_manager.update_account_balance(
                transaction.to_address, to_balance + transaction.value
            )

        # Dispatch a transaction status update to FINALIZED
        ConsensusAlgorithm.dispatch_transaction_status_update(
            transactions_processor,
            transaction.hash,
            TransactionStatus.FINALIZED,
            msg_handler,
        )

        transactions_processor.create_rollup_transaction(transaction.hash)

    def run_appeal_window_loop(
        self,
        chain_snapshot_factory: Callable[
            [Session], ChainSnapshot
        ] = chain_snapshot_factory,
        transactions_processor_factory: Callable[
            [Session], TransactionsProcessor
        ] = transactions_processor_factory,
        accounts_manager_factory: Callable[
            [Session], AccountsManager
        ] = accounts_manager_factory,
        contract_snapshot_factory: Callable[
            [str, Session, Transaction], ContractSnapshot
        ] = contract_snapshot_factory,
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
        stop_event: threading.Event = threading.Event(),
    ):
        """
        Run the loop to handle the appeal window.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            accounts_manager_factory (Callable[[Session], AccountsManager]): Creates managers to handle account state.
            contract_snapshot_factory (Callable[[str, Session, Transaction], ContractSnapshot]): Creates snapshots of contract states.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Creates node instances that can execute contracts and process transactions.
            stop_event (threading.Event): Control signal to terminate the appeal window process.
        """
        # Create a new event loop for running the appeal window
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            self._appeal_window(
                chain_snapshot_factory,
                transactions_processor_factory,
                accounts_manager_factory,
                contract_snapshot_factory,
                node_factory,
                stop_event,
            )
        )
        loop.close()

    async def _appeal_window(
        self,
        chain_snapshot_factory: Callable[[Session], ChainSnapshot],
        transactions_processor_factory: Callable[[Session], TransactionsProcessor],
        accounts_manager_factory: Callable[[Session], AccountsManager],
        contract_snapshot_factory: Callable[
            [str, Session, Transaction], ContractSnapshot
        ],
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
        stop_event: threading.Event,
    ):
        """
        Handle the appeal window for transactions, during which EOAs can challenge transaction results.

        Args:
            chain_snapshot_factory (Callable[[Session], ChainSnapshot]): Creates snapshots of the blockchain state at specific points in time.
            transactions_processor_factory (Callable[[Session], TransactionsProcessor]): Creates processors to modify transactions.
            accounts_manager_factory (Callable[[Session], AccountsManager]): Creates managers to handle account state.
            contract_snapshot_factory (Callable[[str, Session, Transaction], ContractSnapshot]): Creates snapshots of contract states.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Creates node instances that can execute contracts and process transactions.
            stop_event (threading.Event): Control signal to terminate the appeal window process.
        """
        # Set a new event loop for the appeal window
        asyncio.set_event_loop(asyncio.new_event_loop())

        while not stop_event.is_set():
            try:
                async with asyncio.TaskGroup() as tg:
                    with self.get_session() as session:
                        # Get the accepted and undetermined transactions per contract address
                        chain_snapshot = chain_snapshot_factory(session)
                        accepted_undetermined_transactions = (
                            chain_snapshot.get_accepted_undetermined_transactions()
                        )

                        # Iterate over the contracts
                        for (
                            accepted_undetermined_queue
                        ) in accepted_undetermined_transactions.values():

                            # Create a new session for each task so tasks can be run in parallel
                            with self.get_session() as task_session:

                                async def exec_appeal_window_with_session_handling(
                                    task_session: Session,
                                    accepted_undetermined_queue: list[dict],
                                ):
                                    transactions_processor = (
                                        transactions_processor_factory(task_session)
                                    )

                                    # Go through the whole queue to check for appeals and finalizations
                                    for index, transaction in enumerate(
                                        accepted_undetermined_queue
                                    ):
                                        transaction = Transaction.from_dict(transaction)

                                        # Check if the transaction is appealed
                                        if not transaction.appealed:

                                            # Check if the transaction can be finalized
                                            if self.can_finalize_transaction(
                                                transactions_processor,
                                                transaction,
                                                index,
                                                accepted_undetermined_queue,
                                            ):

                                                # Handle transactions that need to be finalized
                                                await self.process_finalization(
                                                    transaction,
                                                    transactions_processor,
                                                    chain_snapshot,
                                                    accounts_manager_factory(
                                                        task_session
                                                    ),
                                                    lambda contract_address: contract_snapshot_factory(
                                                        contract_address,
                                                        task_session,
                                                        transaction,
                                                    ),
                                                    node_factory,
                                                )
                                                task_session.commit()

                                        else:
                                            # Handle transactions that are appealed
                                            if (
                                                transaction.status
                                                == TransactionStatus.UNDETERMINED
                                            ):
                                                # Leader appeal
                                                await self.process_leader_appeal(
                                                    transaction,
                                                    transactions_processor,
                                                    chain_snapshot,
                                                    accounts_manager_factory(
                                                        task_session
                                                    ),
                                                    lambda contract_address: contract_snapshot_factory(
                                                        contract_address,
                                                        task_session,
                                                        transaction,
                                                    ),
                                                    node_factory,
                                                )
                                                task_session.commit()

                                            else:
                                                # Validator appeal
                                                await self.process_validator_appeal(
                                                    transaction,
                                                    transactions_processor,
                                                    chain_snapshot,
                                                    accounts_manager_factory(
                                                        task_session
                                                    ),
                                                    lambda contract_address: contract_snapshot_factory(
                                                        contract_address,
                                                        task_session,
                                                        transaction,
                                                    ),
                                                    node_factory,
                                                )
                                                task_session.commit()

                                tg.create_task(
                                    exec_appeal_window_with_session_handling(
                                        task_session, accepted_undetermined_queue
                                    )
                                )

            except Exception as e:
                print("Error running consensus", e)
                print(traceback.format_exc())
            await asyncio.sleep(self.consensus_sleep_time)

    def can_finalize_transaction(
        self,
        transactions_processor: TransactionsProcessor,
        transaction: Transaction,
        index: int,
        accepted_undetermined_queue: list[dict],
    ) -> bool:
        """
        Check if the transaction can be finalized based on the following criteria:
        - The transaction is a leader only transaction
        - The transaction has exceeded the finality window
        - The previous transaction has been finalized

        Args:
            transactions_processor (TransactionsProcessor): The transactions processor instance.
            transaction (Transaction): The transaction to be possibly finalized.
            index (int): The index of the current transaction in the accepted_undetermined_queue.
            accepted_undetermined_queue (list[dict]): The list of accepted and undetermined transactions for one contract.

        Returns:
            bool: True if the transaction can be finalized, False otherwise.
        """
        if (transaction.leader_only) or (
            (
                int(time.time())
                - transaction.timestamp_awaiting_finalization
                - transaction.appeal_processing_time
            )
            > self.finality_window_time
        ):
            if index == 0:
                return True
            else:
                previous_transaction_hash = accepted_undetermined_queue[index - 1][
                    "hash"
                ]
                previous_transaction = transactions_processor.get_transaction_by_hash(
                    previous_transaction_hash
                )
                if previous_transaction["status"] == TransactionStatus.FINALIZED.value:
                    return True
                else:
                    return False
        else:
            return False

    async def process_finalization(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
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
    ):
        """
        Process the finalization of a transaction.

        Args:
            transaction (Transaction): The transaction to finalize.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        """
        # Create a transaction context for finalizing the transaction
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=self.msg_handler,
        )

        # Transition to the FinalizingState
        state = FinalizingState()
        await state.handle(context)

    async def process_leader_appeal(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
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
    ):
        """
        Process the leader appeal of a transaction.

        Args:
            transaction (Transaction): The transaction to appeal.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        """
        # Create a transaction context for the appeal
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=self.msg_handler,
        )

        transactions_processor.set_transaction_appeal(transaction.hash, False)
        transaction.appealed = False

        used_leader_addresses = (
            ConsensusAlgorithm.get_used_leader_addresses_from_consensus_history(
                context.transactions_processor.get_transaction_by_hash(
                    context.transaction.hash
                )["consensus_history"]
            )
        )
        if len(transaction.consensus_data.validators) + len(
            used_leader_addresses
        ) >= len(chain_snapshot.get_all_validators()):
            self.msg_handler.send_message(
                LogEvent(
                    "consensus_event",
                    EventType.ERROR,
                    EventScope.CONSENSUS,
                    "Appeal failed, no validators found to process the appeal",
                    {
                        "transaction_hash": transaction.hash,
                    },
                    transaction_hash=transaction.hash,
                )
            )
            self.msg_handler.send_message(
                log_event=LogEvent(
                    "transaction_appeal_updated",
                    EventType.INFO,
                    EventScope.CONSENSUS,
                    "Set transaction appealed",
                    {
                        "hash": context.transaction.hash,
                    },
                ),
                log_to_terminal=False,
            )

        else:
            # Appeal data member is used in the frontend for both types of appeals
            # Here the type is refined based on the status
            transactions_processor.set_transaction_appeal_undetermined(
                transaction.hash, True
            )
            transaction.appeal_undetermined = True

            # Begin state transitions starting from PendingState
            state = PendingState()
            while True:
                next_state = await state.handle(context)
                if next_state is None:
                    break
                elif next_state == "leader_appeal_success":
                    self.rollback_transactions(context)
                    break
                state = next_state

    async def process_validator_appeal(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
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
    ):
        """
        Process the validator appeal of a transaction.

        Args:
            transaction (Transaction): The transaction to appeal.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        """
        # Create a transaction context for the appeal
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=self.msg_handler,
        )

        # Set the leader receipt in the context
        context.consensus_data.leader_receipt = (
            transaction.consensus_data.leader_receipt
        )
        try:
            # Attempt to get extra validators for the appeal process
            _, context.remaining_validators = ConsensusAlgorithm.get_extra_validators(
                chain_snapshot.get_all_validators(),
                transaction.consensus_history,
                transaction.consensus_data,
                transaction.appeal_failed,
            )
        except ValueError as e:
            # When no validators are found, then the appeal failed
            context.msg_handler.send_message(
                LogEvent(
                    "consensus_event",
                    EventType.ERROR,
                    EventScope.CONSENSUS,
                    "Appeal failed, no validators found to process the appeal",
                    {
                        "transaction_hash": context.transaction.hash,
                    },
                    transaction_hash=context.transaction.hash,
                )
            )
            context.transactions_processor.set_transaction_appeal(
                context.transaction.hash, False
            )
            context.transaction.appealed = False
            self.msg_handler.send_message(
                log_event=LogEvent(
                    "transaction_appeal_updated",
                    EventType.INFO,
                    EventScope.CONSENSUS,
                    "Set transaction appealed",
                    {
                        "hash": context.transaction.hash,
                    },
                ),
                log_to_terminal=False,
            )
            context.transactions_processor.set_transaction_appeal_processing_time(
                context.transaction.hash
            )
        else:
            # Set up the context for the committing state
            context.num_validators = len(context.remaining_validators)
            context.votes = {}
            context.contract_snapshot_supplier = (
                lambda: context.contract_snapshot_factory(
                    context.transaction.to_address
                )
            )

            # Begin state transitions starting from CommittingState
            state = CommittingState()
            while True:
                next_state = await state.handle(context)
                if next_state is None:
                    break
                elif next_state == "validator_appeal_success":
                    self.rollback_transactions(context)
                    ConsensusAlgorithm.dispatch_transaction_status_update(
                        context.transactions_processor,
                        context.transaction.hash,
                        TransactionStatus.PENDING,
                        context.msg_handler,
                    )

                    # Get the previous state of the contract
                    previous_contact_state = (
                        context.transaction.contract_snapshot.encoded_state
                    )

                    # Restore the contract state
                    if previous_contact_state:
                        # Get the contract snapshot for the transaction's target address
                        leaders_contract_snapshot = context.contract_snapshot_factory(
                            context.transaction.to_address
                        )

                        # Update the contract state with the previous state
                        leaders_contract_snapshot.update_contract_state(
                            accepted_state=previous_contact_state
                        )

                    # Transaction will be picked up by _crawl_snapshot
                    break
                state = next_state

    def rollback_transactions(self, context: TransactionContext):
        """
        Rollback newer transactions.
        """
        # Rollback all future transactions for the current contract
        # Stop the _crawl_snapshot and the _run_consensus for the current contract
        address = context.transaction.to_address
        self.stop_pending_queue_task(address)

        # Wait until task is finished
        while self.is_pending_queue_task_running(address):
            time.sleep(1)

        # Empty the pending queue
        self.pending_queues[address] = asyncio.Queue()

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

            # Reset the contract snapshot for the transaction
            context.transactions_processor.set_transaction_contract_snapshot(
                future_transaction["hash"], None
            )

        # Start the queue loop again
        self.start_pending_queue_task(address)

    @staticmethod
    def get_extra_validators(
        all_validators: List[dict],
        consensus_history: dict,
        consensus_data: ConsensusData,
        appeal_failed: int,
    ):
        """
        Get extra validators for the appeal process according to the following formula:
        - when appeal_failed = 0, add n + 2 validators
        - when appeal_failed > 0, add (2 * appeal_failed * n + 1) + 2 validators
        Note that for appeal_failed > 0, the returned set contains the old validators
        from the previous appeal round and new validators.

        Selection of the extra validators:
        appeal_failed | PendingState | Reused validators | Extra selected     | Total
                      | validators   | from the previous | validators for the | validators
                      |              | appeal round      | appeal             |
        ----------------------------------------------------------------------------------
               0      |       n      |          0        |        n+2         |    2n+2
               1      |       n      |        n+2        |        n+1         |    3n+3
               2      |       n      |       2n+3        |         2n         |    5n+3
               3      |       n      |       4n+3        |         2n         |    7n+3
                              └───────┬──────┘  └─────────┬────────┘
                                      │                   |
        Validators after the ◄────────┘                   └──► Validators during the appeal
        appeal. This equals                                    for appeal_failed > 0
        the Total validators                                   = (2*appeal_failed*n+1)+2
        of the row above,                                      This is the formula from
        and are in consensus_data.                             above and it is what is
        For appeal_failed > 0                                  returned by this function
        = (2*appeal_failed-1)*n+3
        This is used to calculate n

        Args:
            all_validators (List[dict]): List of all validators.
            consensus_history (dict): Dictionary of consensus rounds results and status changes.
            consensus_data (ConsensusData): Data related to the consensus process.
            appeal_failed (int): Number of times the appeal has failed.

        Returns:
            list: List of current validators.
            list: List of extra validators.
        """
        # Get current validators and a dictionary mapping addresses to validators not used in the consensus process
        current_validators, validator_map = (
            ConsensusAlgorithm.get_validators_from_consensus_data(
                all_validators, consensus_data, False
            )
        )

        # Remove used leaders from validator_map
        used_leader_addresses = (
            ConsensusAlgorithm.get_used_leader_addresses_from_consensus_history(
                consensus_history
            )
        )
        for used_leader_address in used_leader_addresses:
            if used_leader_address in validator_map:
                validator_map.pop(used_leader_address)

        # Set not_used_validators to the remaining validators in validator_map
        not_used_validators = list(validator_map.values())

        if len(not_used_validators) == 0:
            raise ValueError("No validators found")

        nb_current_validators = len(current_validators) + 1  # including the leader
        if appeal_failed == 0:
            # Calculate extra validators when no appeal has failed
            extra_validators = get_validators_for_transaction(
                not_used_validators, nb_current_validators + 2
            )
        elif appeal_failed == 1:
            # Calculate extra validators when one appeal has failed
            n = (nb_current_validators - 2) // 2
            extra_validators = get_validators_for_transaction(
                not_used_validators, n + 1
            )
            extra_validators = current_validators[n - 1 :] + extra_validators
        else:
            # Calculate extra validators when more than one appeal has failed
            n = (nb_current_validators - 3) // (2 * appeal_failed - 1)
            extra_validators = get_validators_for_transaction(
                not_used_validators, 2 * n
            )
            extra_validators = current_validators[n - 1 :] + extra_validators

        return current_validators, extra_validators

    @staticmethod
    def get_validators_from_consensus_data(
        all_validators: List[dict], consensus_data: ConsensusData, include_leader: bool
    ):
        """
        Get validators from consensus data.

        Args:
            all_validators (List[dict]): List of all validators.
            consensus_data (ConsensusData): Data related to the consensus process.
            include_leader (bool): Whether to get the leader in the validator set.
        Returns:
            list: List of validators involved in the consensus process (can include the leader).
            dict: Dictionary mapping addresses to validators not used in the consensus process.
        """
        # Create a dictionary to map addresses to a validator
        validator_map = {
            validator["address"]: validator for validator in all_validators
        }

        # Extract address of the leader from consensus data
        if include_leader:
            receipt_addresses = [consensus_data.leader_receipt.node_config["address"]]
        else:
            receipt_addresses = []

        # Extract addresses of validators from consensus data
        receipt_addresses += [
            receipt.node_config["address"] for receipt in consensus_data.validators
        ]

        # Return validators whose addresses are in the receipt addresses
        validators = [
            validator_map.pop(receipt_address)
            for receipt_address in receipt_addresses
            if receipt_address in validator_map
        ]

        return validators, validator_map

    @staticmethod
    def add_new_validator(
        all_validators: List[dict], validators: List[dict], leader_addresses: set[str]
    ):
        """
        Add a new validator to the list of validators.

        Args:
            all_validators (List[dict]): List of all validators.
            validators (list[dict]): List of validators.
            leader_addresses (set[str]): Set of leader addresses.

        Returns:
            list: List of validators.
        """
        # Check if there is a validator to be possibly selected
        if len(leader_addresses) + len(validators) >= len(all_validators):
            raise ValueError("No more validators found to add a new validator")

        # Extract a set of addresses of validators and leaders
        addresses = {validator["address"] for validator in validators}
        addresses.update(leader_addresses)

        # Get not used validators
        not_used_validators = [
            validator
            for validator in all_validators
            if validator["address"] not in addresses
        ]

        # Get new validator
        new_validator = get_validators_for_transaction(not_used_validators, 1)

        return new_validator + validators

    @staticmethod
    def get_used_leader_addresses_from_consensus_history(
        consensus_history: dict, current_leader_receipt: Receipt | None = None
    ):
        """
        Get the used leader addresses from the consensus history.

        Args:
            consensus_history (dict): Dictionary of consensus rounds results and status changes.
            current_leader_receipt (Receipt | None): Current leader receipt.

        Returns:
            set[str]: Set of used leader addresses.
        """
        used_leader_addresses = set()
        if "consensus_results" in consensus_history:
            for consensus_round in consensus_history["consensus_results"]:
                leader_receipt = consensus_round["leader_result"]
                if leader_receipt:
                    used_leader_addresses.update(
                        [leader_receipt["node_config"]["address"]]
                    )

        # consensus_history does not contain the latest consensus_data
        if current_leader_receipt:
            used_leader_addresses.update(
                [current_leader_receipt.node_config["address"]]
            )

        return used_leader_addresses

    def set_finality_window_time(self, time: int):
        """
        Set the finality window time.

        Args:
            time (int): The finality window time.
        """
        self.finality_window_time = time

        # Send log event to update the frontend value
        self.msg_handler.send_message(
            LogEvent(
                name="finality_window_time_updated",
                type=EventType.INFO,
                scope=EventScope.RPC,
                message=f"Finality window time updated to {time}",
                data={"time": time},
            ),
            log_to_terminal=False,
        )


class TransactionState(ABC):
    """
    Abstract base class representing a state in the transaction process.
    """

    @abstractmethod
    async def handle(self, context: TransactionContext):
        """
        Handle the state transition.

        Args:
            context (TransactionContext): The context of the transaction.
        """
        pass


class PendingState(TransactionState):
    """
    Class representing the pending state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the pending state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState | None: The ProposingState or None if the transaction is already in process, when it is a transaction or when there are no validators.
        """
        # Transactions that are put back to pending are processed again, so we need to get the latest data of the transaction
        context.transaction = Transaction.from_dict(
            context.transactions_processor.get_transaction_by_hash(
                context.transaction.hash
            )
        )

        context.msg_handler.send_message(
            LogEvent(
                "consensus_event",
                EventType.INFO,
                EventScope.CONSENSUS,
                "Executing transaction",
                {
                    "transaction_hash": context.transaction.hash,
                    "transaction": context.transaction.to_dict(),
                },
                transaction_hash=context.transaction.hash,
            )
        )

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

        # Retrieve all validators from the snapshot
        all_validators = context.chain_snapshot.get_all_validators()

        # Check if there are validators available
        if not all_validators:
            context.msg_handler.send_message(
                LogEvent(
                    "consensus_event",
                    EventType.ERROR,
                    EventScope.CONSENSUS,
                    "No validators found to process transaction",
                    {
                        "transaction_hash": context.transaction.hash,
                    },
                    transaction_hash=context.transaction.hash,
                )
            )
            return None

        # Determine the involved validators based on whether the transaction is appealed
        if context.transaction.appealed:
            # If the transaction is appealed, remove the old leader
            context.involved_validators, _ = (
                ConsensusAlgorithm.get_validators_from_consensus_data(
                    all_validators, context.transaction.consensus_data, False
                )
            )

            # Reset the transaction appeal status
            context.transactions_processor.set_transaction_appeal(
                context.transaction.hash, False
            )
            context.transaction.appealed = False

        elif context.transaction.appeal_undetermined:
            # Add n+2 validators, remove the old leader
            current_validators, extra_validators = (
                ConsensusAlgorithm.get_extra_validators(
                    all_validators,
                    context.transaction.consensus_history,
                    context.transaction.consensus_data,
                    0,
                )
            )
            context.involved_validators = current_validators + extra_validators

        else:
            # If there was no validator appeal or leader appeal
            if context.transaction.consensus_data:
                # Transaction was rolled back, so we need to reuse the validators and leader
                context.involved_validators, _ = (
                    ConsensusAlgorithm.get_validators_from_consensus_data(
                        all_validators, context.transaction.consensus_data, True
                    )
                )

            else:
                # Transaction was never executed, get the default number of validators for the transaction
                context.involved_validators = get_validators_for_transaction(
                    all_validators, DEFAULT_VALIDATORS_COUNT
                )

        # Transition to the ProposingState
        return ProposingState()


class ProposingState(TransactionState):
    """
    Class representing the proposing state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the proposing state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState: The CommittingState or UndeterminedState if all rotations are done.
        """
        # Dispatch a transaction status update to PROPOSING
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.PROPOSING,
            context.msg_handler,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        # The leader is elected randomly
        random.shuffle(context.involved_validators)

        # Unpack the leader and validators
        [leader, *context.remaining_validators] = context.involved_validators

        # If the transaction is leader-only, clear the validators
        if context.transaction.leader_only:
            context.remaining_validators = []

        # Create a contract snapshot for the transaction
        contract_snapshot_supplier = lambda: context.contract_snapshot_factory(
            context.transaction.to_address
        )

        # Create a leader node for executing the transaction
        leader_node = context.node_factory(
            leader,
            ExecutionMode.LEADER,
            contract_snapshot_supplier(),
            None,
            context.msg_handler,
            context.contract_snapshot_factory,
        )

        # Execute the transaction and obtain the leader receipt
        leader_receipt = await leader_node.exec_transaction(context.transaction)
        votes = {leader["address"]: leader_receipt.vote.value}

        # Update the consensus data with the leader's vote and receipt
        context.consensus_data.votes = votes
        context.consensus_data.leader_receipt = leader_receipt
        context.consensus_data.validators = []
        context.transactions_processor.set_transaction_result(
            context.transaction.hash, context.consensus_data.to_dict()
        )

        # Set the validators and other context attributes
        context.num_validators = len(context.remaining_validators) + 1
        context.contract_snapshot_supplier = contract_snapshot_supplier
        context.votes = votes

        # Transition to the CommittingState
        return CommittingState()


class CommittingState(TransactionState):
    """
    Class representing the committing state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the committing state transition. There are no encrypted votes.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState: The RevealingState.
        """
        # Dispatch a transaction status update to COMMITTING
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.COMMITTING,
            context.msg_handler,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        # Create validator nodes for each validator
        context.validator_nodes = [
            context.node_factory(
                validator,
                ExecutionMode.VALIDATOR,
                (
                    context.transaction.contract_snapshot
                    if context.transaction.contract_snapshot
                    else context.contract_snapshot_supplier()
                ),
                context.consensus_data.leader_receipt,
                context.msg_handler,
                context.contract_snapshot_factory,
            )
            for validator in context.remaining_validators
        ]

        # Execute the transaction on each validator node and gather the results
        sem = asyncio.Semaphore(8)

        async def run_single_validator(validator: Node) -> Receipt:
            async with sem:
                return await validator.exec_transaction(context.transaction)

        validation_tasks = [
            run_single_validator(validator) for validator in context.validator_nodes
        ]
        context.validation_results = await asyncio.gather(*validation_tasks)

        # Transition to the RevealingState
        return RevealingState()


class RevealingState(TransactionState):
    """
    Class representing the revealing state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the revealing state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState | None: The AcceptedState or ProposingState or None if the transaction is successfully appealed.
        """
        # Update the transaction status to REVEALING
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.REVEALING,
            context.msg_handler,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        # Process each validation result and update the context
        for i, validation_result in enumerate(context.validation_results):
            # Store the vote from each validator node
            context.votes[context.validator_nodes[i].address] = (
                validation_result.vote.value
            )

            # Create a dictionary of votes for the current reveal so the rollup transaction contains leader vote and one validator vote (done for each validator)
            # create_rollup_transaction() is removed but we keep this code for future use
            single_reveal_votes = {
                context.consensus_data.leader_receipt.node_config[
                    "address"
                ]: context.consensus_data.leader_receipt.vote.value,
                context.validator_nodes[i].address: validation_result.vote.value,
            }

            # Update consensus data with the current reveal vote and validator
            context.consensus_data.votes = single_reveal_votes
            context.consensus_data.validators = [validation_result]

            # Set the consensus data of the transaction
            context.transactions_processor.set_transaction_result(
                context.transaction.hash, context.consensus_data.to_dict()
            )

        # Determine if the majority of validators agree
        majority_agrees = (
            len([vote for vote in context.votes.values() if vote == Vote.AGREE.value])
            > context.num_validators // 2
        )

        if context.transaction.appealed:

            # Update the consensus results with all new votes and validators
            context.consensus_data.votes = (
                context.transaction.consensus_data.votes | context.votes
            )

            # Overwrite old validator results based on the number of appeal failures
            if context.transaction.appeal_failed == 0:
                context.consensus_data.validators = (
                    context.transaction.consensus_data.validators
                    + context.validation_results
                )

            elif context.transaction.appeal_failed == 1:
                n = (len(context.transaction.consensus_data.validators) - 1) // 2
                context.consensus_data.validators = (
                    context.transaction.consensus_data.validators[: n - 1]
                    + context.validation_results
                )

            else:
                n = len(context.validation_results) - (
                    len(context.transaction.consensus_data.validators) + 1
                )
                context.consensus_data.validators = (
                    context.transaction.consensus_data.validators[: n - 1]
                    + context.validation_results
                )

            if majority_agrees:
                # Appeal failed, increment the appeal_failed counter
                context.transactions_processor.set_transaction_appeal_failed(
                    context.transaction.hash,
                    context.transaction.appeal_failed + 1,
                )
                return AcceptedState()

            else:
                # Appeal succeeded, set the status to PENDING and reset the appeal_failed counter
                context.transactions_processor.set_transaction_result(
                    context.transaction.hash, context.consensus_data.to_dict()
                )

                context.transactions_processor.create_rollup_transaction(
                    context.transaction.hash
                )

                context.transactions_processor.set_transaction_appeal_failed(
                    context.transaction.hash,
                    0,
                )
                context.transactions_processor.update_consensus_history(
                    context.transaction.hash,
                    "Validator Appeal Successful",
                    None,
                    context.validation_results,
                )

                # Reset the appeal processing time
                context.transactions_processor.reset_transaction_appeal_processing_time(
                    context.transaction.hash
                )
                context.transactions_processor.set_transaction_timestamp_appeal(
                    context.transaction.hash, None
                )

                return "validator_appeal_success"

        else:
            # Not appealed, update consensus data with current votes and validators
            context.consensus_data.votes = context.votes
            context.consensus_data.validators = context.validation_results

            if majority_agrees:
                return AcceptedState()

            # If all rotations are done and no consensus is reached, transition to UndeterminedState
            elif context.rotation_count >= context.transaction.config_rotation_rounds:
                return UndeterminedState()

            else:
                used_leader_addresses = (
                    ConsensusAlgorithm.get_used_leader_addresses_from_consensus_history(
                        context.transactions_processor.get_transaction_by_hash(
                            context.transaction.hash
                        )["consensus_history"],
                        context.consensus_data.leader_receipt,
                    )
                )
                # Add a new validator to the list of current validators when a rotation happens
                try:
                    context.involved_validators = ConsensusAlgorithm.add_new_validator(
                        context.chain_snapshot.get_all_validators(),
                        context.remaining_validators,
                        used_leader_addresses,
                    )
                except ValueError as e:
                    # No more validators
                    context.msg_handler.send_message(
                        LogEvent(
                            "consensus_event",
                            EventType.ERROR,
                            EventScope.CONSENSUS,
                            str(e),
                            {
                                "transaction_hash": context.transaction.hash,
                            },
                            transaction_hash=context.transaction.hash,
                        )
                    )
                    return UndeterminedState()

                context.rotation_count += 1

                # Log the failure to reach consensus and transition to ProposingState
                context.msg_handler.send_message(
                    LogEvent(
                        "consensus_event",
                        EventType.INFO,
                        EventScope.CONSENSUS,
                        "Majority disagreement, rotating the leader",
                        {
                            "transaction_hash": context.transaction.hash,
                        },
                        transaction_hash=context.transaction.hash,
                    )
                )

                # Update the consensus history
                if context.transaction.appeal_undetermined:
                    consensus_round = "Leader Rotation Appeal"
                else:
                    consensus_round = "Leader Rotation"
                context.transactions_processor.update_consensus_history(
                    context.transaction.hash,
                    consensus_round,
                    context.consensus_data.leader_receipt,
                    context.validation_results,
                )
                return ProposingState()


class AcceptedState(TransactionState):
    """
    Class representing the accepted state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the accepted state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            None: The transaction is accepted.
        """
        # When appeal fails, the appeal window is not reset
        if context.transaction.appeal_undetermined:
            consensus_round = "Leader Appeal Successful"
            context.transactions_processor.set_transaction_timestamp_awaiting_finalization(
                context.transaction.hash
            )
            context.transactions_processor.reset_transaction_appeal_processing_time(
                context.transaction.hash
            )
            context.transactions_processor.set_transaction_timestamp_appeal(
                context.transaction.hash, None
            )
            context.transaction.timestamp_appeal = None
        elif not context.transaction.appealed:
            consensus_round = "Accepted"
            context.transactions_processor.set_transaction_timestamp_awaiting_finalization(
                context.transaction.hash
            )
        else:
            consensus_round = "Validator Appeal Failed"
            # Set the transaction appeal status to False
            context.transactions_processor.set_transaction_appeal(
                context.transaction.hash, False
            )

            # Increment the appeal processing time when the transaction was appealed
            context.transactions_processor.set_transaction_appeal_processing_time(
                context.transaction.hash
            )

        # Set the transaction result
        context.transactions_processor.set_transaction_result(
            context.transaction.hash, context.consensus_data.to_dict()
        )

        # Update the transaction status to ACCEPTED
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.ACCEPTED,
            context.msg_handler,
        )

        context.transactions_processor.update_consensus_history(
            context.transaction.hash,
            consensus_round,
            (
                None
                if consensus_round == "Validator Appeal Failed"
                else context.consensus_data.leader_receipt
            ),
            context.validation_results,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        # Send a message indicating consensus was reached
        context.msg_handler.send_message(
            LogEvent(
                "consensus_event",
                EventType.SUCCESS,
                EventScope.CONSENSUS,
                "Reached consensus",
                {
                    "transaction_hash": context.transaction.hash,
                    "consensus_data": context.consensus_data.to_dict(),
                },
                transaction_hash=context.transaction.hash,
            )
        )

        # Retrieve the leader's receipt from the consensus data
        leader_receipt = context.consensus_data.leader_receipt

        # Do not deploy or update the contract if validator appeal failed
        if not context.transaction.appealed:
            # Get the contract snapshot for the transaction's target address
            leaders_contract_snapshot = context.contract_snapshot_supplier()

            # Set the contract snapshot for the transaction for a future rollback
            context.transactions_processor.set_transaction_contract_snapshot(
                context.transaction.hash, leaders_contract_snapshot.to_dict()
            )

            # Do not deploy or update the contract if the execution failed
            if leader_receipt.execution_result == ExecutionResultStatus.SUCCESS:
                # Register contract if it is a new contract
                if context.transaction.type == TransactionType.DEPLOY_CONTRACT:
                    new_contract = {
                        "id": context.transaction.data["contract_address"],
                        "data": {
                            "state": {
                                "accepted": leader_receipt.contract_state,
                                "finalized": {},
                            },
                            "code": context.transaction.data["contract_code"],
                            "ghost_contract_address": context.transaction.ghost_contract_address,
                        },
                    }
                    leaders_contract_snapshot.register_contract(new_contract)

                    # Send a message indicating successful contract deployment
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
                        accepted_state=leader_receipt.contract_state
                    )

                _emit_transactions(
                    context, leader_receipt.pending_transactions, "accepted"
                )

        else:
            context.transaction.appealed = False

        # Set the transaction appeal undetermined status to false and return appeal status
        if context.transaction.appeal_undetermined:
            context.transactions_processor.set_transaction_appeal_undetermined(
                context.transaction.hash, False
            )
            context.transaction.appeal_undetermined = False
            return "leader_appeal_success"
        else:
            return None


class UndeterminedState(TransactionState):
    """
    Class representing the undetermined state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the undetermined state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            None: The transaction remains in an undetermined state.
        """
        # Send a message indicating consensus failure
        context.msg_handler.send_message(
            LogEvent(
                "consensus_event",
                EventType.ERROR,
                EventScope.CONSENSUS,
                "Failed to reach consensus",
                {
                    "transaction_hash": context.transaction.hash,
                    "consensus_data": context.consensus_data.to_dict(),
                },
                transaction_hash=context.transaction.hash,
            )
        )

        # When appeal fails, the appeal window is not reset
        if not context.transaction.appeal_undetermined:
            context.transactions_processor.set_transaction_timestamp_awaiting_finalization(
                context.transaction.hash
            )

        # Set the transaction appeal undetermined status to false
        if context.transaction.appeal_undetermined:
            context.transactions_processor.set_transaction_appeal_undetermined(
                context.transaction.hash, False
            )
            context.transaction.appeal_undetermined = False
            consensus_round = "Leader Appeal Failed"
        else:
            consensus_round = "Undetermined"

        # Set the transaction result with the current consensus data
        context.transactions_processor.set_transaction_result(
            context.transaction.hash,
            context.consensus_data.to_dict(),
        )

        # Increment the appeal processing time when the transaction was appealed
        if context.transaction.timestamp_appeal is not None:
            context.transactions_processor.set_transaction_appeal_processing_time(
                context.transaction.hash
            )

        # Update the transaction status to undetermined
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.UNDETERMINED,
            context.msg_handler,
        )

        context.transactions_processor.update_consensus_history(
            context.transaction.hash,
            consensus_round,
            context.consensus_data.leader_receipt,
            context.consensus_data.validators,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        return None


class FinalizingState(TransactionState):
    """
    Class representing the finalizing state of a transaction.
    """

    async def handle(self, context):
        """
        Handle the finalizing state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            None: The transaction is finalized.
        """
        # Retrieve the leader's receipt from the consensus data
        leader_receipt = context.transaction.consensus_data.leader_receipt

        # Update contract state
        if (context.transaction.status == TransactionStatus.ACCEPTED) and (
            leader_receipt.execution_result == ExecutionResultStatus.SUCCESS
        ):
            # Get the contract snapshot for the transaction's target address
            leaders_contract_snapshot = context.contract_snapshot_factory(
                context.transaction.to_address
            )
            leaders_contract_snapshot.update_contract_state(
                finalized_state=leader_receipt.contract_state
            )

        # Update the transaction status to FINALIZED
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.FINALIZED,
            context.msg_handler,
        )

        context.transactions_processor.create_rollup_transaction(
            context.transaction.hash
        )

        if context.transaction.status != TransactionStatus.UNDETERMINED:
            # Insert pending transactions generated by contract-to-contract calls
            _emit_transactions(
                context,
                context.transaction.consensus_data.leader_receipt.pending_transactions,
                "finalized",
            )


def _emit_transactions(
    context: TransactionContext,
    pending_transactions: Iterable[PendingTransaction],
    on: Literal["accepted", "finalized"],
):
    for pending_transaction in filter(lambda t: t.on == on, pending_transactions):
        nonce = context.transactions_processor.get_transaction_count(
            context.transaction.to_address
        )
        data: dict
        transaction_type: TransactionType
        if pending_transaction.is_deploy():
            transaction_type = TransactionType.DEPLOY_CONTRACT
            new_contract_address: str
            if pending_transaction.salt_nonce == 0:
                # NOTE: this address is random, which doesn't 100% align with consensus spec
                new_contract_address = (
                    context.accounts_manager.create_new_account().address
                )
            else:
                from eth_utils.crypto import keccak
                from backend.node.types import Address
                from backend.node.base import SIMULATOR_CHAIN_ID

                arr = bytearray()
                arr.append(1)
                arr.extend(Address(context.transaction.to_address).as_bytes)
                arr.extend(
                    pending_transaction.salt_nonce.to_bytes(32, "big", signed=False)
                )
                arr.extend(SIMULATOR_CHAIN_ID.to_bytes(32, "big", signed=False))
                new_contract_address = Address(keccak(arr)[:20]).as_hex
                context.accounts_manager.create_new_account_with_address(
                    new_contract_address
                )
            pending_transaction.address = new_contract_address
            data = {
                "contract_address": new_contract_address,
                "contract_code": pending_transaction.code,
                "calldata": pending_transaction.calldata,
            }
        else:
            transaction_type = TransactionType.RUN_CONTRACT
            data = {
                "calldata": pending_transaction.calldata,
            }
        context.transactions_processor.insert_transaction(
            context.transaction.to_address,  # new calls are done by the contract
            pending_transaction.address,
            data,
            value=0,  # we only handle EOA transfers at the moment, so no value gets transferred
            type=transaction_type.value,
            nonce=nonce,
            leader_only=context.transaction.leader_only,  # Cascade
            triggered_by_hash=context.transaction.hash,
        )
