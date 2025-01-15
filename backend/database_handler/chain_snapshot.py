# database_handler/chain_snapshot.py

from typing import List
from sqlalchemy.orm import Session

from backend.database_handler.transactions_processor import (
    TransactionStatus,
    Transactions,
)
from .transactions_processor import TransactionsProcessor
from backend.database_handler.validators_registry import ValidatorsRegistry


class ChainSnapshot:
    def __init__(self, session: Session):
        self.session = session
        self.validators_registry = ValidatorsRegistry(session)
        self.all_validators = self.validators_registry.get_all_validators()
        self.pending_transactions = self._load_pending_transactions()
        self.num_validators = len(self.all_validators)
        self.accepted_transactions = self._load_accepted_transactions()

    def _load_pending_transactions(self) -> List[dict]:
        """Load and return the list of pending transactions from the database."""

        pending_transactions = (
            self.session.query(Transactions)
            .filter(Transactions.status == TransactionStatus.PENDING)
            .all()
        )
        return [
            TransactionsProcessor._parse_transaction_data(transaction)
            for transaction in pending_transactions
        ]

    def get_pending_transactions(self):
        """Return the list of pending transactions."""
        return self.pending_transactions

    def get_all_validators(self):
        """Return the list of all validators."""
        return self.all_validators

    def _load_accepted_transactions(self) -> List[dict]:
        """Load and return the list of accepted transactions from the database."""

        accepted_transactions = (
            self.session.query(Transactions)
            .filter(Transactions.status == TransactionStatus.ACCEPTED)
            .all()
        )
        return [
            TransactionsProcessor._parse_transaction_data(transaction)
            for transaction in accepted_transactions
        ]

    def get_accepted_transactions(self):
        """Return the list of accepted transactions."""
        return self.accepted_transactions
