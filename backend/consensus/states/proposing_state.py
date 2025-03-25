import random
from backend.database_handler.transactions_processor import TransactionStatus
from backend.node.types import ExecutionMode
from backend.consensus.states.transaction_state import TransactionState
from backend.consensus.states.committing_state import CommittingState
from backend.consensus.algorithm.transaction_status import TransactionStatusManager
from copy import deepcopy


class ProposingState(TransactionState):

    async def handle(self, context):
        """
        Handle the proposing state transition.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState: The CommittingState or UndeterminedState if all rotations are done.
        """

        # Dispatch a transaction status update to PROPOSING
        TransactionStatusManager.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.PROPOSING,
            context.msg_handler,
        )

        # context.transactions_processor.create_rollup_transaction(
        #     context.transaction.hash
        # )

        # The leader is elected randomly
        random.shuffle(context.involved_validators)

        # Unpack the leader and validators
        [leader, *context.remaining_validators] = context.involved_validators

        # If the transaction is leader-only, clear the validators
        if context.transaction.leader_only:
            context.remaining_validators = []

        # Copy contract snapshot if it exists, otherwise create one
        if context.transaction.contract_snapshot:
            contract_snapshot = deepcopy(context.transaction.contract_snapshot)
        else:
            contract_snapshot_supplier = lambda: context.contract_snapshot_factory(
                context.transaction.to_address
            )
            context.contract_snapshot_supplier = contract_snapshot_supplier
            contract_snapshot = contract_snapshot_supplier()

        # Create a leader node for executing the transaction
        leader_node = context.node_factory(
            leader,
            ExecutionMode.LEADER,
            contract_snapshot,
            None,
            context.msg_handler,
            context.contract_snapshot_factory,
        )

        # Execute the transaction and obtain the leader receipt
        leader_receipt = await leader_node.exec_transaction(context.transaction)
        votes = {leader["address"]: leader_receipt.vote.value}

        # Update the consensus data with the leader's vote and receipt
        context.consensus_data.votes = votes
        context.consensus_data.leader_receipt = leader_receipt
        context.consensus_data.validators = []
        context.transactions_processor.set_transaction_result(
            context.transaction.hash, context.consensus_data.to_dict()
        )

        # Set the validators and other context attributes
        context.num_validators = len(context.remaining_validators) + 1
        context.votes = votes

        # Transition to the CommittingState
        return CommittingState()
