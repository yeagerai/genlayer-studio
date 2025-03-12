from backend.consensus.vrf import get_validators_for_transaction
from backend.domain.types import (
    Transaction,
    TransactionType,
)
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)
from backend.consensus.base import TransactionState
from backend.consensus.base import DEFAULT_VALIDATORS_COUNT
from backend.consensus.states.proposing_state import ProposingState


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
        from backend.consensus.helpers.consensus_algorithm import ConsensusAlgorithm

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
