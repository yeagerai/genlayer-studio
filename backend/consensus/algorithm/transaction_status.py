from backend.database_handler.transactions_processor import (
    TransactionStatus,
    TransactionsProcessor,
)
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)


class TransactionStatusManager:
    @staticmethod
    def dispatch_transaction_status_update(
        transactions_processor: TransactionsProcessor,
        transaction_hash: str,
        new_status: TransactionStatus,
        msg_handler,
    ):
        """
        Dispatch a transaction status update.

        Args:
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            transaction_hash (str): Hash of the transaction.
            new_status (TransactionStatus): New status of the transaction.
            msg_handler: Handler for messaging.
        """
        transactions_processor.update_transaction_status(transaction_hash, new_status)
        msg_handler.send_message(
            LogEvent(
                "transaction_status_updated",
                EventType.INFO,
                EventScope.CONSENSUS,
                f"{str(new_status.value)} {str(transaction_hash)}",
                {
                    "hash": str(transaction_hash),
                    "new_status": str(new_status.value),
                },
                transaction_hash=transaction_hash,
            )
        )
