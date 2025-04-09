import asyncio
from typing import Callable
from sqlalchemy.orm import Session
from backend.domain.types import Transaction
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.protocol_rpc.message_handler.base import MessageHandler
from .transaction_status import TransactionStatusManager
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.contract_processor import ContractProcessor
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.pending_state import PendingState
from backend.rollup.consensus_service import ConsensusService
import threading
import time
import traceback


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
        msg_handler (MessageHandler): Handler for messaging.
    """
    # Check if the transaction is a fund_account call
    if not transaction.from_address is None:
        # Get the balance of the sender account
        from_balance = accounts_manager.get_account_balance(transaction.from_address)

        # Check if the sender has enough balance
        if from_balance < transaction.value:
            # Set the transaction status to UNDETERMINED if balance is insufficient
            TransactionStatusManager.dispatch_transaction_status_update(
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

    # Check if the transaction is a burn call
    if not transaction.to_address is None:
        # Get the balance of the recipient account
        to_balance = accounts_manager.get_account_balance(transaction.to_address)

        # Update the balance of the recipient account
        accounts_manager.update_account_balance(
            transaction.to_address, to_balance + transaction.value
        )

    # Dispatch a transaction status update to FINALIZED
    TransactionStatusManager.dispatch_transaction_status_update(
        transactions_processor,
        transaction.hash,
        TransactionStatus.FINALIZED,
        msg_handler,
    )

    # transactions_processor.create_rollup_transaction(transaction.hash)


class TransactionProcessor:
    @staticmethod
    async def process_pending_transactions(
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
        get_session: Callable[[], Session],
        pending_queues: dict[str, asyncio.Queue],
        pending_queue_stop_events: dict[str, asyncio.Event],
        pending_queue_task_running: dict[str, bool],
        msg_handler: MessageHandler,
        consensus_service: ConsensusService,
        consensus_sleep_time: float,
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
                    for queue_address, queue in pending_queues.items():
                        if (
                            not queue.empty()
                            and not pending_queue_stop_events.get(
                                queue_address, asyncio.Event()
                            ).is_set()
                        ):
                            # Sessions cannot be shared between coroutines; create a new session for each coroutine
                            # Reference: https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks
                            pending_queue_task_running[queue_address] = True
                            transaction: Transaction = await queue.get()
                            with get_session() as session:

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
                                        msg_handler,
                                        consensus_service,
                                    )
                                    session.commit()
                                    pending_queue_task_running[queue_address] = False

                            tg.create_task(
                                exec_transaction_with_session_handling(
                                    session, transaction, queue_address
                                )
                            )

            except Exception as e:
                print("Error running consensus", e)
                print(traceback.format_exc())
            finally:
                for queue_address in pending_queues:
                    pending_queue_task_running[queue_address] = False
            await asyncio.sleep(consensus_sleep_time)

    @staticmethod
    async def exec_transaction(
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
        accounts_manager: AccountsManager,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
        contract_processor: ContractProcessor,
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
            contract_processor=contract_processor,
            node_factory=node_factory,
            msg_handler=msg_handler,
            consensus_service=consensus_service,
        )

        # Begin state transitions starting from PendingState
        state = PendingState()
        while True:
            next_state = await state.handle(context)
            if next_state is None:
                break
            state = next_state

    @staticmethod
    def rollback_transactions(
        context: TransactionContext,
        pending_queues: dict[str, asyncio.Queue],
        is_pending_queue_task_running: Callable[[str], bool],
        start_pending_queue_task: Callable[[str], None],
        stop_pending_queue_task: Callable[[str], None],
    ):
        """
        Rollback newer transactions.

        Args:
            context (TransactionContext): The context of the transaction.
            pending_queues (dict[str, asyncio.Queue]): The pending queues for transactions.
            is_pending_queue_task_running (Callable[[str], bool]): Function to check if a task is running.
            stop_pending_queue_task (Callable[[str], None]): Function to stop the pending queue task.
            start_pending_queue_task: Callable[[], None]:  Function to start the pending queue loop.
        """
        # Rollback all future transactions for the current contract
        address = context.transaction.to_address
        stop_pending_queue_task(address)

        # Wait until task is finished
        while is_pending_queue_task_running(address):
            time.sleep(1)

        # Empty the pending queue
        pending_queues[address] = asyncio.Queue()

        # Set all transactions with higher created_at to PENDING
        future_transactions = context.transactions_processor.get_newer_transactions(
            context.transaction.hash
        )
        for future_transaction in future_transactions:
            TransactionStatusManager.dispatch_transaction_status_update(
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
        start_pending_queue_task(address)
