from abc import ABC, abstractmethod
from backend.consensus.helpers.transaction_context import TransactionContext


class TransactionState(ABC):
    @abstractmethod
    async def handle(self, context: TransactionContext):
        """
        Handle the state transition.

        Args:
            context (TransactionContext): The context of the transaction.
        """
        pass
