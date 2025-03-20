from typing import Callable, List
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.types import ConsensusData
from backend.domain.types import Transaction
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.message_handler.types import LogEvent, EventType, EventScope
from backend.consensus.helpers.vrf import get_validators_for_transaction
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.pending_state import PendingState
from backend.consensus.states.committing_state import CommittingState
from backend.consensus.algorithm.transaction_processor import process_transaction
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

            await process_transaction(context, PendingState)

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
            _, context.remaining_validators = AppealProcessor.get_extra_validators(
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

            # state = CommittingState(state_name="CommittingState")
            await process_transaction(
                context,
                CommittingState,
                transactions_processor=transactions_processor,
                state_name="CommittingState",
            )

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

    @staticmethod
    def get_extra_validators(
        all_validators: List[dict],
        consensus_history: dict,
        consensus_data: ConsensusData,
        appeal_failed: int,
    ):
        """Get extra validators for the appeal process."""
        current_validators, validator_map = (
            ValidatorManagement.get_validators_from_consensus_data(
                all_validators, consensus_data, False
            )
        )

        used_leader_addresses = (
            ValidatorManagement.get_used_leader_addresses_from_consensus_history(
                consensus_history
            )
        )
        for used_leader_address in used_leader_addresses:
            if used_leader_address in validator_map:
                validator_map.pop(used_leader_address)

        not_used_validators = list(validator_map.values())

        if len(not_used_validators) == 0:
            raise ValueError("No validators found")

        nb_current_validators = len(current_validators) + 1
        if appeal_failed == 0:
            extra_validators = get_validators_for_transaction(
                not_used_validators, nb_current_validators + 2
            )
        elif appeal_failed == 1:
            n = (nb_current_validators - 2) // 2
            extra_validators = get_validators_for_transaction(
                not_used_validators, n + 1
            )
            extra_validators = current_validators[n - 1 :] + extra_validators
        else:
            n = (nb_current_validators - 3) // (2 * appeal_failed - 1)
            extra_validators = get_validators_for_transaction(
                not_used_validators, 2 * n
            )
            extra_validators = current_validators[n - 1 :] + extra_validators

        return current_validators, extra_validators

    # @staticmethod
    # def get_used_leader_addresses_from_consensus_history(
    #     consensus_history: dict,
    #     current_leader_receipt: Receipt | None = None,
    # ):
    #     """Get the used leader addresses from the consensus history."""
    #     used_leader_addresses = set()
    #     if "consensus_results" in consensus_history:
    #         for consensus_round in consensus_history["consensus_results"]:
    #             leader_receipt = consensus_round["leader_result"]
    #             if leader_receipt:
    #                 used_leader_addresses.update(
    #                     [leader_receipt["node_config"]["address"]]
    #                 )
    #
    #     if current_leader_receipt:
    #         used_leader_addresses.update(
    #             [current_leader_receipt.node_config["address"]]
    #         )
    #
    #     return used_leader_addresses
