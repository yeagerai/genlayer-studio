from backend.database_handler.transactions_processor import TransactionStatus
from backend.node.types import Vote
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)
from backend.consensus.states.transaction_state import TransactionState
from backend.consensus.states.accepted_state import AcceptedState
from backend.consensus.states.undetermined_state import UndeterminedState


class RevealingState(TransactionState):

    async def handle(self, context):
        """
        Handle the revealing state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState | None: The AcceptedState or ProposingState or None if the transaction is successfully appealed.
        """
        from backend.consensus.consensus_algorithm import ConsensusAlgorithm
        from backend.consensus.states.proposing_state import ProposingState

        # Update the transaction status to REVEALING
        ConsensusAlgorithm.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.REVEALING,
            context.msg_handler,
        )

        # context.transactions_processor.create_rollup_transaction(
        #     context.transaction.hash
        # )

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

                # context.transactions_processor.create_rollup_transaction(
                #     context.transaction.hash
                # )

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
