from backend.database_handler.transactions_processor import TransactionStatus
from backend.domain.types import TransactionType
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)
from backend.node.types import ExecutionResultStatus
from backend.consensus.helpers.utils import _emit_transactions
from backend.consensus.states.transaction_state import TransactionState
from backend.consensus.algorithm.transaction_status import TransactionStatusManager


class AcceptedState(TransactionState):

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
        TransactionStatusManager.dispatch_transaction_status_update(
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

        # context.transactions_processor.create_rollup_transaction(
        #     context.transaction.hash
        # )

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

        # Contract won't be deployed or updated if validator appeal fails. But if transaction didn't come
        # from a validator appeal, a leader appeal will deploy/update the contract.
        if not context.transaction.appealed:
            # Get the contract snapshot for the transaction's target address
            leaders_contract_snapshot = context.contract_snapshot

            # Set the contract snapshot for the transaction for a future rollback
            if not context.transaction.contract_snapshot:
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
                    context.contract_processor.update_contract_state(
                        context.transaction.to_address,
                        accepted_state=leader_receipt.contract_state,
                    )

                _emit_transactions(
                    context, leader_receipt.pending_transactions, "accepted"
                )

        else:
            context.transaction.appealed = False

        # Set the transaction appeal undetermined status to false and return appeal status
        if context.transaction.appeal_undetermined:
            context.transaction.appeal_undetermined = (
                context.transactions_processor.set_transaction_appeal_undetermined(
                    context.transaction.hash, False
                )
            )
            return "leader_appeal_success"
        else:
            return None
