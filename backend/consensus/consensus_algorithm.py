import os
import asyncio
import traceback
import threading
from typing import Callable
from sqlalchemy.orm import Session
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.contract_processor import ContractProcessor
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.domain.types import Transaction
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.message_handler.types import LogEvent, EventType, EventScope
from backend.consensus.helpers.factories import (
    chain_snapshot_factory,
    transactions_processor_factory,
    accounts_manager_factory,
    contract_snapshot_factory,
    contract_processor_factory,
    node_factory,
    DEFAULT_CONSENSUS_SLEEP_TIME,
)
from backend.consensus.algorithm.transaction_processor import TransactionProcessor
from backend.consensus.algorithm.appeal_processor import AppealProcessor
from backend.consensus.algorithm.finalization_processor import FinalizationProcessor
from backend.consensus.algorithm.transaction_status import TransactionStatusManager
from backend.rollup.consensus_service import ConsensusService


class ConsensusAlgorithm:
    def __init__(
        self,
        get_session: Callable[[], Session],
        msg_handler: MessageHandler,
        consensus_service: ConsensusService,
    ):
        """
        Initialize the ConsensusAlgorithm.

        Args:
            get_session (Callable[[], Session]): Function to get a database session.
            msg_handler (MessageHandler): Handler for messaging.
        """
        self.get_session = get_session
        self.msg_handler = msg_handler
        self.consensus_service = consensus_service
        self.pending_queues: dict[str, asyncio.Queue] = {}
        self.finality_window_time = int(os.getenv("VITE_FINALITY_WINDOW"))
        self.finality_window_appeal_failed_reduction = float(
            os.getenv("VITE_FINALITY_WINDOW_APPEAL_FAILED_REDUCTION")
        )
        self.consensus_sleep_time = DEFAULT_CONSENSUS_SLEEP_TIME
        self.pending_queue_stop_events: dict[str, asyncio.Event] = (
            {}
        )  # Events to stop tasks for each pending queue
        self.pending_queue_task_running: dict[str, bool] = (
            {}
        )  # Track running state for each pending queue

    def is_pending_queue_task_running(self, address: str):
        """Check if a task for a specific pending queue is currently running."""
        return self.pending_queue_task_running.get(address, False)

    def stop_pending_queue_task(self, address: str):
        """Signal the task for a specific pending queue to stop."""
        if address in self.pending_queues:
            if address not in self.pending_queue_stop_events:
                self.pending_queue_stop_events[address] = asyncio.Event()
            self.pending_queue_stop_events[address].set()

    def start_pending_queue_task(self, address: str):
        """Allow the task for a specific pending queue to start."""
        if address in self.pending_queue_stop_events:
            self.pending_queue_stop_events[address].clear()

    def set_finality_window_time(self, time: int):
        """Set the finality window time."""
        self.finality_window_time = time
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
        """Run the loop to crawl snapshots."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            self._crawl_snapshot(
                chain_snapshot_factory,
                transactions_processor_factory,
                stop_event,
            )
        )
        loop.close()

    async def _crawl_snapshot(
        self,
        chain_snapshot_factory: Callable[[Session], ChainSnapshot],
        transactions_processor_factory: Callable[[Session], TransactionsProcessor],
        stop_event: threading.Event,
    ):
        """Crawl snapshots and process pending transactions."""
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
                        TransactionStatusManager.dispatch_transaction_status_update(
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
        contract_processor_factory: Callable[
            [Session], ContractProcessor
        ] = contract_processor_factory,
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
        msg_handler: MessageHandler = MessageHandler,
        consensus_service: ConsensusService = ConsensusService,
        stop_event: threading.Event = threading.Event(),
    ):
        """Run the process pending transactions loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            TransactionProcessor.process_pending_transactions(
                chain_snapshot_factory,
                transactions_processor_factory,
                accounts_manager_factory,
                contract_snapshot_factory,
                contract_processor_factory,
                node_factory,
                self.get_session,
                self.pending_queues,
                self.pending_queue_stop_events,
                self.pending_queue_task_running,
                self.msg_handler,
                consensus_service,
                self.consensus_sleep_time,
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
        contract_processor_factory: Callable[[Session], ContractProcessor],
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
        consensus_service: ConsensusService,
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
                                    await TransactionProcessor.exec_transaction(
                                        transaction,
                                        transactions_processor,
                                        chain_snapshot_factory(session),
                                        accounts_manager_factory(session),
                                        lambda contract_address: contract_snapshot_factory(
                                            contract_address, session, transaction
                                        ),
                                        contract_processor_factory(session),
                                        node_factory,
                                        self.msg_handler,
                                        self.consensus_service,
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
        contract_processor_factory: Callable[
            [Session], ContractProcessor
        ] = contract_processor_factory,
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
        msg_handler: MessageHandler = MessageHandler,
        consensus_service: ConsensusService = ConsensusService,
        stop_event: threading.Event = threading.Event(),
    ):
        """Run the loop to handle the appeal window."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            self._appeal_window(
                chain_snapshot_factory,
                transactions_processor_factory,
                accounts_manager_factory,
                contract_snapshot_factory,
                contract_processor_factory,
                node_factory,
                msg_handler,
                consensus_service,
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
        contract_processor_factory: Callable[[Session], ContractProcessor],
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
        consensus_service: ConsensusService,
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
                                            if FinalizationProcessor.can_finalize_transaction(
                                                transactions_processor,
                                                transaction,
                                                index,
                                                accepted_undetermined_queue,
                                                self.finality_window_time,
                                                self.finality_window_appeal_failed_reduction,
                                            ):
                                                # Handle transactions that need to be finalized
                                                await FinalizationProcessor.process_finalization(
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
                                                    contract_processor_factory(
                                                        task_session
                                                    ),
                                                    node_factory,
                                                    self.msg_handler,
                                                    self.consensus_service,
                                                )
                                                task_session.commit()
                                                print(
                                                    "COMMITTED PROCESSING FINALIZATION!!!"
                                                )

                                        else:
                                            # Handle transactions that are appealed
                                            if (
                                                transaction.status
                                                == TransactionStatus.UNDETERMINED
                                            ):
                                                # Leader appeal
                                                await AppealProcessor.process_leader_appeal(
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
                                                    contract_processor_factory(
                                                        task_session
                                                    ),
                                                    node_factory,
                                                    msg_handler,
                                                    consensus_service,
                                                    self.pending_queues,
                                                    self.is_pending_queue_task_running,
                                                    self.start_pending_queue_task,
                                                    self.stop_pending_queue_task,
                                                )
                                                task_session.commit()

                                            else:
                                                # Validator appeal
                                                await AppealProcessor.process_validator_appeal(
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
                                                    contract_processor_factory(
                                                        task_session
                                                    ),
                                                    node_factory,
                                                    msg_handler,
                                                    consensus_service,
                                                    self.pending_queues,
                                                    self.is_pending_queue_task_running,
                                                    self.start_pending_queue_task,
                                                    self.stop_pending_queue_task,
                                                )
                                                task_session.commit()

                                print("creating task queue now for undetermined...")
                                tg.create_task(
                                    exec_appeal_window_with_session_handling(
                                        task_session, accepted_undetermined_queue
                                    )
                                )

            except Exception as e:
                print("Error running consensus", e)
                print(traceback.format_exc())
            await asyncio.sleep(self.consensus_sleep_time)
