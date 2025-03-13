from backend.database_handler.transactions_processor import TransactionStatus
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)
from backend.consensus.base import TransactionState


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
        from backend.consensus.helpers.consensus_algorithm import ConsensusAlgorithm

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

        # Save the contract snapshot for potential future appeals
        if not context.transaction.contract_snapshot:
            context.transactions_processor.set_transaction_contract_snapshot(
                context.transaction.hash, context.contract_snapshot_supplier().to_dict()
            )

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

        # context.transactions_processor.create_rollup_transaction(
        #     context.transaction.hash
        # )

        return None
