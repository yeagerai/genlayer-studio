import asyncio
from backend.database_handler.transactions_processor import TransactionStatus
from backend.node.base import Node
from backend.node.types import (
    ExecutionMode,
    Receipt,
)
from backend.consensus.states.transaction_state import TransactionState
from backend.consensus.states.revealing_state import RevealingState
from backend.consensus.algorithm.transaction_status import TransactionStatusManager


class CommittingState(TransactionState):

    async def handle(self, context):
        """
        Handle the committing state transition. There are no encrypted votes.

        Args:
            context (TransactionContext): The context of the transaction.

        Returns:
            TransactionState: The RevealingState.
        """
        # Dispatch a transaction status update to COMMITTING
        TransactionStatusManager.dispatch_transaction_status_update(
            context.transactions_processor,
            context.transaction.hash,
            TransactionStatus.COMMITTING,
            context.msg_handler,
        )

        # context.transactions_processor.create_rollup_transaction(
        #     context.transaction.hash
        # )

        # Create validator nodes for each validator
        context.validator_nodes = [
            context.node_factory(
                validator,
                ExecutionMode.VALIDATOR,
                (
                    context.transaction.contract_snapshot
                    if context.transaction.contract_snapshot
                    else context.contract_snapshot
                ),
                context.consensus_data.leader_receipt,
                context.msg_handler,
                context.contract_snapshot_factory,
            )
            for validator in context.remaining_validators
        ]

        # Execute the transaction on each validator node and gather the results
        sem = asyncio.Semaphore(8)

        async def run_single_validator(validator: Node) -> Receipt:
            async with sem:
                return await validator.exec_transaction(context.transaction)

        validation_tasks = [
            run_single_validator(validator) for validator in context.validator_nodes
        ]
        context.validation_results = await asyncio.gather(*validation_tasks)

        # Transition to the RevealingState
        return RevealingState()
