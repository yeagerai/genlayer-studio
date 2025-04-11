import asyncio
from typing import Callable, List
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
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.pending_state import PendingState
from backend.consensus.states.committing_state import CommittingState
from backend.consensus.algorithm.transaction_processor import TransactionProcessor
from backend.consensus.algorithm.transaction_status import TransactionStatusManager
from backend.consensus.algorithm.validator_management import ValidatorManagement
from backend.rollup.consensus_service import ConsensusService


class AppealProcessor:
    @staticmethod
    async def process_leader_appeal(
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
        pending_queues: dict[str, asyncio.Queue],
        is_pending_queue_task_running: Callable[[str], bool],
        start_pending_queue_task: Callable[[str], None],
        stop_pending_queue_task: Callable[[str], None],
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
            contract_processor=contract_processor,
            node_factory=node_factory,
            msg_handler=msg_handler,
            consensus_service=consensus_service,
        )

        transactions_processor.set_transaction_appeal(transaction.hash, False)
        transaction.appealed = False

        used_leader_addresses = (
            ValidatorManagement.get_used_leader_addresses_from_consensus_history(
                context.transactions_processor.get_transaction_by_hash(
                    context.transaction.hash
                )["consensus_history"]
            )
        )
        if len(transaction.consensus_data.validators) + len(
            used_leader_addresses
        ) >= len(chain_snapshot.get_all_validators()):
            msg_handler.send_message(
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
            msg_handler.send_message(
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

            context.contract_snapshot_supplier = (
                lambda: context.contract_snapshot_factory(
                    context.transaction.to_address
                )
            )

            # Begin state transitions starting from PendingState
            state = PendingState()
            while True:
                next_state = await state.handle(context)
                if next_state is None:
                    break
                elif next_state == "leader_appeal_success":
                    TransactionProcessor.rollback_transactions(
                        context,
                        pending_queues,
                        is_pending_queue_task_running,
                        stop_pending_queue_task,
                        start_pending_queue_task,
                    )
                    break
                state = next_state

    @staticmethod
    async def process_validator_appeal(
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
        pending_queues: dict[str, asyncio.Queue],
        is_pending_queue_task_running: Callable[[str], bool],
        start_pending_queue_task: Callable[[str], None],
        stop_pending_queue_task: Callable[[str], None],
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
            contract_processor=contract_processor,
            node_factory=node_factory,
            msg_handler=msg_handler,
            consensus_service=consensus_service,
        )

        # Set the leader receipt in the context
        context.consensus_data.leader_receipt = (
            transaction.consensus_data.leader_receipt
        )
        try:
            # Attempt to get extra validators for the appeal process
            _, context.remaining_validators = ValidatorManagement.get_extra_validators(
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
            msg_handler.send_message(
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

            # Send events in rollup to communicate the appeal is started
            context.consensus_service.emit_transaction_event(
                "emitAppealStarted",
                context.remaining_validators[0],
                context.transaction.hash,
                context.remaining_validators[0]["address"],
                0,
                [v["address"] for v in context.remaining_validators],
            )

            # Begin state transitions starting from CommittingState
            state = CommittingState()
            while True:
                next_state = await state.handle(context)
                if next_state is None:
                    break
                elif next_state == "validator_appeal_success":
                    TransactionProcessor.rollback_transactions(
                        context,
                        pending_queues,
                        is_pending_queue_task_running,
                        start_pending_queue_task,
                        stop_pending_queue_task,
                    )
                    TransactionStatusManager.dispatch_transaction_status_update(
                        context.transactions_processor,
                        context.transaction.hash,
                        TransactionStatus.PENDING,
                        context.msg_handler,
                    )

                    # Get the previous state of the contract
                    if context.transaction.contract_snapshot:
                        previous_contact_state = (
                            context.transaction.contract_snapshot.encoded_state
                        )
                    else:
                        previous_contact_state = {}

                    # Restore the contract state
                    context.contract_processor.update_contract_state(
                        context.transaction.to_address,
                        accepted_state=previous_contact_state,
                    )

                    # Reset the contract snapshot for the transaction
                    context.transactions_processor.set_transaction_contract_snapshot(
                        context.transaction.hash, None
                    )

                    # Transaction will be picked up by _crawl_snapshot
                    break
                state = next_state
