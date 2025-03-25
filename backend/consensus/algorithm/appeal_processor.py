from typing import Callable, List
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.accounts_manager import AccountsManager
from backend.domain.types import Transaction
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.message_handler.types import LogEvent, EventType, EventScope
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.pending_state import PendingState
from backend.consensus.states.committing_state import CommittingState
from backend.consensus.algorithm import transaction_processor
from backend.consensus.algorithm.validator_management import ValidatorManagement


class AppealProcessor:
    @staticmethod
    async def process_leader_appeal(
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
        """Process the leader appeal of a transaction."""
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=msg_handler,
        )

        transaction.appealed = transactions_processor.set_transaction_appeal(
            transaction.hash, False
        )

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
                    {"transaction_hash": transaction.hash},
                    transaction_hash=transaction.hash,
                )
            )
            msg_handler.send_message(
                log_event=LogEvent(
                    "transaction_appeal_updated",
                    EventType.INFO,
                    EventScope.CONSENSUS,
                    "Set transaction appealed",
                    {"hash": context.transaction.hash},
                ),
                log_to_terminal=False,
            )
        else:
            transaction.appeal_undetermined = (
                transactions_processor.set_transaction_appeal_undetermined(
                    transaction.hash, True
                )
            )
            context.contract_snapshot_supplier = (
                lambda: context.contract_snapshot_factory(
                    context.transaction.to_address
                )
            )

            await transaction_processor.process_transaction(context, PendingState)

    @staticmethod
    async def process_validator_appeal(
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
        """Process the validator appeal of a transaction."""
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=msg_handler,
        )

        context.consensus_data.leader_receipt = (
            transaction.consensus_data.leader_receipt
        )
        try:
            _, context.remaining_validators = ValidatorManagement.get_extra_validators(
                chain_snapshot.get_all_validators(),
                transaction.consensus_history,
                transaction.consensus_data,
                transaction.appeal_failed,
            )
        except ValueError:
            context.msg_handler.send_message(
                LogEvent(
                    "consensus_event",
                    EventType.ERROR,
                    EventScope.CONSENSUS,
                    "Appeal failed, no validators found to process the appeal",
                    {"transaction_hash": context.transaction.hash},
                    transaction_hash=context.transaction.hash,
                )
            )

            context.transaction.appealed = (
                context.transactions_processor.set_transaction_appeal(
                    context.transaction.hash, False
                )
            )
            msg_handler.send_message(
                log_event=LogEvent(
                    "transaction_appeal_updated",
                    EventType.INFO,
                    EventScope.CONSENSUS,
                    "Set transaction appealed",
                    {"hash": context.transaction.hash},
                ),
                log_to_terminal=False,
            )
            context.transactions_processor.set_transaction_appeal_processing_time(
                context.transaction.hash
            )
        else:
            context.num_validators = len(context.remaining_validators)
            context.votes = {}
            context.contract_snapshot_supplier = (
                lambda: context.contract_snapshot_factory(
                    context.transaction.to_address
                )
            )

            await transaction_processor.process_transaction(
                context,
                CommittingState,
                transactions_processor=transactions_processor,
            )
