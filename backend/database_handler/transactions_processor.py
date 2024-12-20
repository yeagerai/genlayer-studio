# consensus/services/transactions_db_service.py
from enum import Enum
import rlp

from .models import Transactions
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from .models import TransactionStatus
from eth_utils import to_bytes, keccak, is_address
import json
import base64
import time
from backend.domain.types import TransactionType
from web3 import Web3
from backend.database_handler.contract_snapshot import ContractSnapshot
import os

from backend.rollup.consensus_service import ConsensusService


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

        # Connect to Hardhat Network
        port = os.environ.get("HARDHAT_PORT")
        url = os.environ.get("HARDHAT_URL")
        hardhat_url = f"{url}:{port}"
        self.web3 = Web3(Web3.HTTPProvider(hardhat_url))

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
            "ghost_contract_address": transaction_data.ghost_contract_address,
            "appealed": transaction_data.appealed,
            "timestamp_accepted": transaction_data.timestamp_accepted,
            "appeal_failed": transaction_data.appeal_failed,
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
        ghost_contract_address = None

        if type == TransactionType.DEPLOY_CONTRACT.value:
            # Hardhat account
            account = self.web3.eth.accounts[0]
            private_key = os.environ.get("HARDHAT_PRIVATE_KEY")

            # Ghost contract
            # Read contract ABI and bytecode from compiled contract
            try:
                consensus_service = ConsensusService()
                ghost_contract = consensus_service._load_contract("GhostContract")

                abi = ghost_contract["abi"]
                bytecode = ghost_contract["bytecode"]
                contract = self.web3.eth.contract(abi=abi, bytecode=bytecode)

                # Create the contract instance
                contract = self.web3.eth.contract(abi=abi, bytecode=bytecode)

                # Build the transaction
                gas_estimate = self.web3.eth.estimate_gas(
                    contract.constructor().build_transaction(
                        {
                            "from": account,
                            "nonce": self.web3.eth.get_transaction_count(account),
                            "gasPrice": 0,
                        }
                    )
                )
                transaction = contract.constructor().build_transaction(
                    {
                        "from": account,
                        "nonce": self.web3.eth.get_transaction_count(account),
                        "gas": gas_estimate,
                        "gasPrice": 0,
                    }
                )

                # Sign the transaction
                signed_tx = self.web3.eth.account.sign_transaction(
                    transaction, private_key=private_key
                )

                # Send the transaction
                tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)

                # Wait for the transaction receipt
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
                ghost_contract_address = receipt.contractAddress

            except Exception as e:
                print(f"Error deploying ghost contract: {e}")

        elif type == TransactionType.RUN_CONTRACT.value:
            genlayer_contract_address = to_address
            contract_snapshot = ContractSnapshot(
                genlayer_contract_address, self.session
            )
            ghost_contract_address = contract_snapshot.ghost_contract_address

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
            ghost_contract_address=ghost_contract_address,
            appealed=False,
            timestamp_accepted=None,
            appeal_failed=0,
        )

        self.session.add(new_transaction)

        self.session.flush()  # So that `created_at` gets set

        if type != TransactionType.SEND.value:
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
        self.session.commit()

    def create_rollup_transaction(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        rollup_input_data = json.dumps(
            self._parse_transaction_data(transaction)
        ).encode("utf-8")

        # Hardhat transaction
        account = self.web3.eth.accounts[0]
        private_key = os.environ.get("HARDHAT_PRIVATE_KEY")

        try:
            gas_estimate = self.web3.eth.estimate_gas(
                {
                    "from": account,
                    "to": transaction.ghost_contract_address,
                    "value": transaction.value,
                    "data": rollup_input_data,
                }
            )

            transaction = {
                "from": account,
                "to": transaction.ghost_contract_address,
                "value": transaction.value,
                "data": rollup_input_data,
                "nonce": self.web3.eth.get_transaction_count(account),
                "gas": gas_estimate,
                "gasPrice": 0,
            }

            # Sign and send the transaction
            signed_tx = self.web3.eth.account.sign_transaction(
                transaction, private_key=private_key
            )
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Wait for transaction to be actually mined and get the receipt
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

            # Get full transaction details including input data
            transaction = self.web3.eth.get_transaction(tx_hash)

        except Exception as e:
            print(f"Error creating rollup transaction: {e}")

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

    def set_transaction_appeal_failed(self, transaction_hash: str, appeal_failed: int):
        if appeal_failed < 0:
            raise ValueError("appeal_failed must be a non-negative integer")
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appeal_failed = appeal_failed
