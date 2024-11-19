# consensus/services/transactions_db_service.py
from enum import Enum
import rlp

from .models import Transactions, RollupTransactions
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from .models import TransactionStatus
from eth_utils import to_bytes, keccak, is_address
import json
import base64
import time


class TransactionAddressFilter(Enum):
    ALL = "all"
    TO = "to"
    FROM = "from"


class TransactionsProcessor:
    def __init__(
        self,
        session: Session,
    ):
        self.session = session

    @staticmethod
    def _parse_transaction_data(transaction_data: Transactions) -> dict:
        return {
            "hash": transaction_data.hash,
            "from_address": transaction_data.from_address,
            "to_address": transaction_data.to_address,
            "data": transaction_data.data,
            "value": transaction_data.value,
            "type": transaction_data.type,
            "status": transaction_data.status.value,
            "consensus_data": transaction_data.consensus_data,
            "gaslimit": transaction_data.nonce,
            "nonce": transaction_data.nonce,
            "r": transaction_data.r,
            "s": transaction_data.s,
            "v": transaction_data.v,
            "created_at": transaction_data.created_at.isoformat(),
            "leader_only": transaction_data.leader_only,
            "triggered_by": transaction_data.triggered_by_hash,
            "triggered_transactions": [
                transaction.hash
                for transaction in transaction_data.triggered_transactions
            ],
            "appealed": transaction_data.appealed,
            "timestamp_accepted": transaction_data.timestamp_accepted,
        }

    @staticmethod
    def _transaction_data_to_str(data: dict) -> str:
        """
        NOTE: json doesn't support bytes object, so they need to be encoded somehow
            Common approaches can be: array, hex string, base64 string
            Array takes a lot of space (extra comma for each element)
            Hex is double in size
            Base64 is 1.33 in size
            So base64 is chosen
        """

        def data_encode(d):
            if isinstance(d, bytes):
                return str(base64.b64encode(d), encoding="ascii")
            raise TypeError("Can't encode #{d}")

        return json.dumps(data, default=data_encode)

    @staticmethod
    def _generate_transaction_hash(
        from_address: str,
        to_address: str,
        data: dict,
        value: float,
        type: int,
        nonce: int,
    ) -> str:
        from_address_bytes = (
            to_bytes(hexstr=from_address) if is_address(from_address) else None
        )
        to_address_bytes = (
            to_bytes(hexstr=to_address) if is_address(to_address) else None
        )

        data_bytes = to_bytes(text=TransactionsProcessor._transaction_data_to_str(data))

        tx_elements = [
            from_address_bytes,
            to_address_bytes,
            to_bytes(hexstr=hex(int(value))),
            data_bytes,
            to_bytes(hexstr=hex(type)),
            to_bytes(hexstr=hex(nonce)),
            to_bytes(hexstr=hex(0)),  # gas price (placeholder)
            to_bytes(hexstr=hex(0)),  # gas limit (placeholder)
        ]

        # Filter out None values
        tx_elements = [elem for elem in tx_elements if elem is not None]
        rlp_encoded = rlp.encode(tx_elements)
        hash = "0x" + keccak(rlp_encoded).hex()
        return hash

    def insert_transaction(
        self,
        from_address: str,
        to_address: str,
        data: dict,
        value: float,
        type: int,
        nonce: int,
        leader_only: bool,
        triggered_by_hash: (
            str | None
        ) = None,  # If filled, the transaction must be present in the database (committed)
    ) -> str:
        current_nonce = self.get_transaction_count(from_address)

        if nonce != current_nonce:
            raise Exception(
                f"Unexpected nonce. Provided: {nonce}, expected: {current_nonce}"
            )

        transaction_hash = self._generate_transaction_hash(
            from_address, to_address, data, value, type, nonce
        )

        new_transaction = Transactions(
            hash=transaction_hash,
            from_address=from_address,
            to_address=to_address,
            data=json.loads(self._transaction_data_to_str(data)),
            value=value,
            type=type,
            status=TransactionStatus.PENDING,
            consensus_data=None,  # Will be set when the transaction is finalized
            nonce=nonce,
            # Future fields, unused for now
            gaslimit=None,
            input_data=None,
            r=None,
            s=None,
            v=None,
            leader_only=leader_only,
            triggered_by=(
                self.session.query(Transactions).filter_by(hash=triggered_by_hash).one()
                if triggered_by_hash
                else None
            ),
            appealed=False,
            timestamp_accepted=None,
        )

        self.session.add(new_transaction)

        self.session.flush()  # So that `created_at` gets set

        self.create_rollup_transaction(new_transaction.hash)

        return new_transaction.hash

    def get_transaction_by_hash(self, transaction_hash: str) -> dict | None:
        transaction = (
            self.session.query(Transactions)
            .filter_by(hash=transaction_hash)
            .one_or_none()
        )

        if transaction is None:
            return None

        return self._parse_transaction_data(transaction)

    def update_transaction_status(
        self, transaction_hash: str, new_status: TransactionStatus
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.status = new_status
        self.session.commit()

    def set_transaction_result(self, transaction_hash: str, consensus_data: dict):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.consensus_data = consensus_data

    def create_rollup_transaction(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        rollup_input_data = self._transaction_data_to_str(
            self._parse_transaction_data(transaction)
        )
        rollup_nonce = int(time.time() * 1000)
        rollup_transaction_hash = self._generate_transaction_hash(
            transaction.from_address,
            transaction.to_address,
            rollup_input_data,
            transaction.value,
            0,
            rollup_nonce,
        )
        rollup_transaction_record = RollupTransactions(
            transaction_hash=rollup_transaction_hash,
            from_=transaction.from_address,
            to_=transaction.to_address,
            gas=0,
            gas_price=0,
            value=transaction.value,
            input=rollup_input_data,
            nonce=rollup_nonce,
        )
        self.session.add(rollup_transaction_record)

    def get_transaction_count(self, address: str) -> int:
        count = (
            self.session.query(Transactions)
            .filter(Transactions.from_address == address)
            .count()
        )
        return count

    def get_transactions_for_address(
        self,
        address: str,
        filter: TransactionAddressFilter,
    ) -> list[dict]:
        query = self.session.query(Transactions)

        if filter == TransactionAddressFilter.TO:
            query = query.filter(Transactions.to_address == address)
        elif filter == TransactionAddressFilter.FROM:
            query = query.filter(Transactions.from_address == address)
        else:  # TransactionFilter.ALL
            query = query.filter(
                or_(
                    Transactions.from_address == address,
                    Transactions.to_address == address,
                )
            )

        transactions = query.order_by(Transactions.created_at.desc()).all()

        return [
            self._parse_transaction_data(transaction) for transaction in transactions
        ]

    def set_transaction_appeal(self, transaction_hash: str, appeal: bool):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appealed = appeal

    def set_transaction_timestamp_accepted(
        self, transaction_hash: str, timestamp_accepted: int = None
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        if timestamp_accepted:
            transaction.timestamp_accepted = timestamp_accepted
        else:
            transaction.timestamp_accepted = int(time.time())
