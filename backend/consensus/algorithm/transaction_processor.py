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
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.pending_state import PendingState
from backend.consensus.states.transaction_state import TransactionState
import asyncio


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
        msg_handler (MessageHandler): The message handler.
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

            # transactions_processor.create_rollup_transaction(transaction.hash)
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


async def process_transaction(
    context: TransactionContext,
    initial_state_class: TransactionState,
    transactions_processor: TransactionsProcessor = None,
):
    """
    Process a transaction through state transitions.

    Args:
        context (TransactionContext): The transaction context.
        initial_state_class: The initial state class to start with.
    """
    state = initial_state_class()
    while True:
        next_state = await state.handle(context)
        if next_state is None:
            break
        elif next_state == "leader_appeal_success":
            TransactionProcessor.rollback_transactions(context)
            break
        elif next_state == "validator_appeal_success":
            TransactionProcessor.rollback_transactions(context)
            transactions_processor.update_transaction_status(
                context.transaction.hash,
                TransactionStatus.PENDING,
            )

            previous_contact_state = context.transaction.contract_snapshot.encoded_state
            if previous_contact_state:
                leaders_contract_snapshot = context.contract_snapshot_factory(
                    context.transaction.to_address
                )
                leaders_contract_snapshot.update_contract_state(
                    accepted_state=previous_contact_state
                )
            break
        state = next_state


class TransactionProcessor:
    @staticmethod
    async def process_pending_transactions(
        get_session: Callable[[], Session],
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
        pending_queues: dict[str, asyncio.Queue],
        pending_queue_stop_events: dict[str, asyncio.Event],
        pending_queue_task_running: dict[str, bool],
        msg_handler: MessageHandler,
        consensus_sleep_time: float,
        stop_event: asyncio.Event,
    ):
        """Process pending transactions."""
        asyncio.set_event_loop(asyncio.new_event_loop())
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
                                        node_factory,
                                        msg_handler,
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
        """Execute a transaction."""
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=msg_handler,
        )

        await process_transaction(context, PendingState)

    @staticmethod
    def rollback_transactions(context: TransactionContext):
        """Rollback newer transactions."""
        address = context.transaction.to_address
        future_transactions = context.transactions_processor.get_newer_transactions(
            context.transaction.hash
        )
        for future_transaction in future_transactions:
            context.transactions_processor.update_transaction_status(
                future_transaction["hash"],
                TransactionStatus.PENDING,
            )
            context.transactions_processor.set_transaction_contract_snapshot(
                future_transaction["hash"], None
            )
