# consensus/services/transactions_db_service.py
from datetime import datetime
from enum import Enum
import rlp
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from sqlalchemy.orm.attributes import flag_modified

from backend.node.types import Vote, Receipt
from .models import Transactions, TransactionStatus
from eth_utils import to_bytes, keccak, is_address
import json
import base64
import time
from backend.domain.types import TransactionType
from web3 import Web3
import os


class TransactionAddressFilter(Enum):
    ALL = "all"
    TO = "to"
    FROM = "from"


def vote_name_to_number(vote_name: str | None) -> int:
    """Convert vote name to numeric code.

    Args:
        vote_name: Vote name (AGREE, DISAGREE, etc.)

    Returns:
        int: Numeric vote code (1=AGREE, 2=DISAGREE, 0=other)
    """
    if vote_name is None:
        return 0
    if vote_name.lower() == Vote.AGREE.value:
        return 1
    if vote_name.lower() == Vote.DISAGREE.value:
        return 2
    return 0


def votes_to_result(votes: list) -> str:
    """Determine consensus result from vote list.

    Args:
        votes: List of vote strings

    Returns:
        tuple: (result_code, result_name)
    """
    if len(votes) == 0:
        return "5", "NO_MAJORITY"
    if (
        len([vote for vote in votes if vote.lower() == Vote.AGREE.value])
        > len(votes) // 2
    ):
        return "6", "MAJORITY_AGREE"
    return "7", "MAJORITY_DISAGREE"


def get_validator_vote_hash(validator_address: str, vote_type: int, nonce: int) -> str:
    """
    Generate a hash for validator vote data using Solidity keccak.

    Args:
        validator_address: Address of the validator
        vote_type: Numeric vote type (1=AGREE, 2=DISAGREE, etc.)
        nonce: Transaction nonce

    Returns:
        str: Hex-encoded hash with 0x prefix
    """
    vote_hash_bytes = Web3.solidity_keccak(
        ["address", "uint8", "uint256"], [validator_address, vote_type, nonce]
    )
    return Web3.to_hex(vote_hash_bytes)


def get_tx_execution_hash(leader_address: str, vote_type: int) -> str:
    """
    Generate a hash for transaction execution data using Solidity keccak.

    Args:
        leader_address: Address of the consensus leader
        vote_type: Numeric vote type

    Returns:
        str: Hex-encoded hash with 0x prefix
    """
    tx_execution_hash_bytes = Web3.solidity_keccak(
        ["address", "uint8", "bytes32", "uint256"],
        [leader_address, vote_type, b"", 4444],
    )
    return Web3.to_hex(tx_execution_hash_bytes)


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
        if transaction_data.consensus_data:
            leader_receipts = transaction_data.consensus_data.get("leader_receipt", [])
            if isinstance(leader_receipts, dict):
                result = leader_receipts.get("result", {})
            elif isinstance(leader_receipts, list) and len(leader_receipts) > 0:
                result = leader_receipts[0].get("result", {})
            else:
                result = {}
        else:
            result = transaction_data.consensus_data
        if isinstance(result, dict):
            result = result.get("raw", {})
        return {
            "hash": transaction_data.hash,
            "from_address": transaction_data.from_address,
            "to_address": transaction_data.to_address,
            "data": transaction_data.data,
            "value": transaction_data.value,
            "type": transaction_data.type,
            "status": transaction_data.status.value,
            "result": TransactionsProcessor._decode_base64_data(result),
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
            "timestamp_awaiting_finalization": transaction_data.timestamp_awaiting_finalization,
            "appeal_failed": transaction_data.appeal_failed,
            "appeal_undetermined": transaction_data.appeal_undetermined,
            "consensus_history": transaction_data.consensus_history,
            "timestamp_appeal": transaction_data.timestamp_appeal,
            "appeal_processing_time": transaction_data.appeal_processing_time,
            "contract_snapshot": transaction_data.contract_snapshot,
            "config_rotation_rounds": transaction_data.config_rotation_rounds,
            "num_of_initial_validators": transaction_data.num_of_initial_validators,
            "last_vote_timestamp": transaction_data.last_vote_timestamp,
            "rotation_count": transaction_data.rotation_count,
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
    def _decode_base64_data(data: dict | str) -> dict | str:
        def decode_value(value):
            """Helper function to decode Base64-encoded values if they are strings."""
            if (
                isinstance(value, str)
                and value
                and bool(re.compile(r"^[A-Za-z0-9+/]*={0,2}$").fullmatch(value)) is True
            ):
                try:
                    decoded_str = base64.b64decode(
                        bytes(value, encoding="utf-8")
                    ).decode("utf-8", errors="ignore")
                    byte_content = re.sub(r"^[\x00-\x1f]+", "", decoded_str)
                    if byte_content or len(byte_content) >= 0:
                        return byte_content
                    return decoded_str
                except (ValueError, UnicodeDecodeError):
                    return value  # Return original if decoding fails

            return value  # Return unchanged for non-strings

        if isinstance(data, dict):
            data = {k: decode_value(v) for k, v in data.items()}
            return data
        elif isinstance(data, str):
            data = decode_value(data)
            return data
        elif data is None:
            return None
        else:
            raise TypeError(f"Can't decode unsupported type: {type(data).__name__}")

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
        config_rotation_rounds: int,
        triggered_by_hash: (
            str | None
        ) = None,  # If filled, the transaction must be present in the database (committed)
        transaction_hash: str | None = None,
        num_of_initial_validators: int | None = None,
    ) -> str:
        current_nonce = self.get_transaction_count(from_address)

        # Follow up: https://github.com/MetaMask/metamask-extension/issues/29787
        # to uncomment this check
        # if nonce != current_nonce:
        #     raise Exception(
        #         f"Unexpected nonce. Provided: {nonce}, expected: {current_nonce}"
        #     )

        if transaction_hash is None:
            transaction_hash = self._generate_transaction_hash(
                from_address, to_address, data, value, type, current_nonce
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
            timestamp_awaiting_finalization=None,
            appeal_failed=0,
            appeal_undetermined=False,
            consensus_history={},
            timestamp_appeal=None,
            appeal_processing_time=0,
            contract_snapshot=None,
            config_rotation_rounds=config_rotation_rounds,
            num_of_initial_validators=num_of_initial_validators,
            last_vote_timestamp=None,
            rotation_count=0,
        )

        self.session.add(new_transaction)

        self.session.flush()  # So that `created_at` gets set

        return new_transaction.hash

    def _process_round_data(self, transaction_data: dict) -> dict:
        """Process round data and prepare transaction data."""

        if "consensus_results" in transaction_data["consensus_history"]:
            transaction_data["num_of_rounds"] = str(
                len(transaction_data["consensus_history"]["consensus_results"])
            )
        else:
            transaction_data["num_of_rounds"] = "0"

        validator_votes_name = []
        validator_votes = []
        validator_votes_hash = []
        round_validators = []
        if "consensus_results" in transaction_data["consensus_history"]:
            round_number = str(
                len(transaction_data["consensus_history"]["consensus_results"]) - 1
            )
            last_round = transaction_data["consensus_history"]["consensus_results"][-1]
            if "leader_result" in last_round and last_round["leader_result"]:
                leader = last_round["leader_result"][1]
                validator_votes_name.append(leader["vote"].upper())
                vote_number = vote_name_to_number(leader["vote"])
                validator_votes.append(vote_number)
                leader_address = leader["node_config"]["address"]
                validator_votes_hash.append(
                    get_validator_vote_hash(
                        leader_address, vote_number, transaction_data["nonce"]
                    )
                )
                round_validators.append(leader_address)

            for validator in last_round["validator_results"]:
                validator_votes_name.append(validator["vote"].upper())
                vote_number = vote_name_to_number(validator["vote"])
                validator_votes.append(vote_number)
                validator_address = validator["node_config"]["address"]
                validator_votes_hash.append(
                    get_validator_vote_hash(
                        validator_address, vote_number, transaction_data["nonce"]
                    )
                )
                round_validators.append(validator_address)
        else:
            round_number = "0"
        last_round_result, _ = votes_to_result(validator_votes_name)

        transaction_data["last_round"] = {
            "round": round_number,
            "leader_index": "0",
            "votes_committed": str(len(validator_votes_name)),
            "votes_revealed": str(len(validator_votes_name)),
            "appeal_bond": "0",
            "rotations_left": str(
                transaction_data.get("config_rotation_rounds", 0)
                - transaction_data.get("rotation_count", 0)
            ),
            "result": last_round_result,
            "round_validators": round_validators,
            "validator_votes_hash": validator_votes_hash,
            "validator_votes": validator_votes,
            "validator_votes_name": validator_votes_name,
        }
        return transaction_data

    def _prepare_basic_transaction_data(self, transaction_data: dict) -> dict:
        """Prepare basic transaction data with common fields."""
        transaction_data["current_timestamp"] = str(round(time.time()))
        transaction_data["sender"] = transaction_data["from_address"]
        transaction_data["recipient"] = transaction_data["to_address"]
        transaction_data["tx_slot"] = "0"
        transaction_data["created_timestamp"] = str(
            int(datetime.fromisoformat(transaction_data["created_at"]).timestamp())
        )
        transaction_data["last_vote_timestamp"] = str(
            transaction_data.get("last_vote_timestamp", 0)
        )
        transaction_data["random_seed"] = "0x" + "0" * 64
        transaction_data["tx_id"] = transaction_data["hash"]

        transaction_data["read_state_block_range"] = {
            "activation_block": "0",
            "processing_block": "0",
            "proposal_block": "0",
        }
        if "consensus_results" in transaction_data["consensus_history"]:
            transaction_data["activator"] = transaction_data["consensus_history"][
                "consensus_results"
            ][0]["leader_result"][0]["node_config"]["address"]
        else:
            transaction_data["activator"] = ""

        if (transaction_data["consensus_data"] is not None) and (
            "leader_receipt" in transaction_data["consensus_data"]
        ):
            transaction_data["last_leader"] = transaction_data["consensus_data"][
                "leader_receipt"
            ][0]["node_config"]["address"]
        else:
            transaction_data["last_leader"] = ""
        return transaction_data

    def _encode_transaction_data(self, transaction_data: dict) -> dict:
        to_encode = []
        if transaction_data["data"] is not None:
            if "calldata" in transaction_data["data"]:
                encoded_call_data = base64.b64decode(
                    transaction_data["data"]["calldata"]
                )
                to_encode.append(encoded_call_data)
                to_encode.append(b"\x00")
            if "contract_code" in transaction_data["data"]:
                contract_code_bytes = base64.b64decode(
                    transaction_data["data"]["contract_code"]
                )
                to_encode.insert(0, contract_code_bytes)
        if len(to_encode) == 0:
            transaction_data["tx_data"] = ""
        else:
            transaction_data["tx_data"] = Web3.to_hex(rlp.encode(to_encode))[2:]
        return transaction_data

    def _process_execution_hash(self, transaction_data: dict) -> dict:
        if (
            transaction_data["consensus_data"] is not None
            and "leader_receipt" in transaction_data["consensus_data"]
            and "node_config" in transaction_data["consensus_data"]["leader_receipt"][0]
        ):
            transaction_data["tx_execution_hash"] = get_tx_execution_hash(
                transaction_data["consensus_data"]["leader_receipt"][0]["node_config"][
                    "address"
                ],
                vote_name_to_number(
                    transaction_data["consensus_data"]["leader_receipt"][0]["vote"]
                ),
            )
        else:
            transaction_data["tx_execution_hash"] = ""

        return transaction_data

    def _process_messages(self, transaction_data: dict) -> dict:
        eq_output = []
        if (
            "consensus_history" in transaction_data
            and "consensus_results" in transaction_data["consensus_history"]
        ):
            for consensus_round in transaction_data["consensus_history"][
                "consensus_results"
            ]:
                if consensus_round["leader_result"] is not None:
                    eq_output.append(
                        [
                            len(eq_output),  # key
                            [
                                base64.b64decode(
                                    consensus_round["leader_result"][0]["result"]
                                )[
                                    0
                                ],  # kind
                                "\x00",
                            ],
                        ]
                    )  # data

        kind = 0
        if (
            transaction_data["consensus_data"] is not None
            and "leader_receipt" in transaction_data["consensus_data"]
            and "result" in transaction_data["consensus_data"]["leader_receipt"]
        ):
            kind = base64.b64decode(
                transaction_data["consensus_data"]["leader_receipt"][0]["result"]
            )[0]
        pending_transactions = []
        messages = []
        if (
            transaction_data["consensus_data"] is not None
            and "leader_receipt" in transaction_data["consensus_data"]
            and transaction_data["consensus_data"]["leader_receipt"] is not None
            and "pending_transactions"
            in transaction_data["consensus_data"]["leader_receipt"][0]
            and transaction_data["consensus_data"]["leader_receipt"][0][
                "pending_transactions"
            ]
            is not None
        ):
            for message in transaction_data["consensus_data"]["leader_receipt"][0][
                "pending_transactions"
            ]:
                pending_transactions.append(
                    [
                        message.get("address", ""),  # Account
                        message.get("calldata", ""),  # Calldata
                        message.get("value", 0),  # Value
                        message.get("on", "finalized"),  # On
                        message.get("code", ""),  # Code
                        message.get("salt_nonce", 0),  # SaltNonce
                    ]
                )
                messages.append(
                    {
                        "messageType": "0",
                        "recipient": message.get("address", ""),
                        "value": message.get("value", 0),
                        "data": message.get("calldata", ""),
                        "onAcceptance": message.get("on", "finalized") == "accepted",
                    }
                )
        transaction_data["eq_blocks_outputs"] = Web3.to_hex(
            rlp.encode(
                [
                    [
                        [kind, "\x00"],  # data
                        pending_transactions,
                        [],  # pending eth transactions
                        bytes.fromhex(""),
                    ],  # storage proof
                    eq_output,
                ]
            )
        )
        transaction_data["messages"] = messages
        return transaction_data

    def _process_queue(self, transaction_data: dict) -> dict:
        status_to_queue_type = {
            TransactionStatus.PENDING.value: "1",
            TransactionStatus.ACTIVATED.value: "1",
            TransactionStatus.ACCEPTED.value: "2",
            TransactionStatus.UNDETERMINED.value: "3",
        }
        transaction_data["queue_type"] = status_to_queue_type.get(
            transaction_data["status"], "0"
        )
        transaction_data["queue_position"] = "0"

        return transaction_data

    def _process_result(self, transaction_data: dict) -> dict:
        if (transaction_data["consensus_data"] is not None) and (
            "votes" in transaction_data["consensus_data"]
        ):
            votes_temp = transaction_data["consensus_data"]["votes"].values()
        else:
            votes_temp = []
        transaction_data["result"], transaction_data["result_name"] = votes_to_result(
            votes_temp
        )
        return transaction_data

    def get_transaction_by_hash(self, transaction_hash: str) -> dict | None:
        transaction = (
            self.session.query(Transactions)
            .filter_by(hash=transaction_hash)
            .one_or_none()
        )

        if transaction is None:
            return None

        transaction_data = self._parse_transaction_data(transaction)

        # Process for testnet
        transaction_data = self._prepare_basic_transaction_data(transaction_data)
        transaction_data = self._process_result(transaction_data)
        transaction_data = self._encode_transaction_data(transaction_data)
        transaction_data = self._process_execution_hash(transaction_data)
        transaction_data = self._process_messages(transaction_data)
        transaction_data = self._process_queue(transaction_data)
        transaction_data = self._process_round_data(transaction_data)
        return transaction_data

    def update_transaction_status(
        self,
        transaction_hash: str,
        new_status: TransactionStatus,
        update_current_status_changes: bool = True,
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.status = new_status

        if update_current_status_changes:
            if not transaction.consensus_history:
                transaction.consensus_history = {}

            if "current_status_changes" in transaction.consensus_history:
                transaction.consensus_history["current_status_changes"].append(
                    new_status.value
                )
            else:
                transaction.consensus_history["current_status_changes"] = [
                    TransactionStatus.PENDING.value,
                    new_status.value,
                ]
            flag_modified(transaction, "consensus_history")

        self.session.commit()

    def set_transaction_result(
        self, transaction_hash: str, consensus_data: dict | None
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.consensus_data = consensus_data
        self.session.commit()

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
        # You can only appeal the transaction if it is in accepted or undetermined state
        # Setting it to false is always allowed
        if not appeal:
            transaction.appealed = appeal
            self.session.commit()
        elif transaction.status in (
            TransactionStatus.ACCEPTED,
            TransactionStatus.UNDETERMINED,
        ):
            transaction.appealed = appeal
            self.set_transaction_timestamp_appeal(transaction, int(time.time()))
            self.session.commit()

    def set_transaction_timestamp_awaiting_finalization(
        self, transaction_hash: str, timestamp_awaiting_finalization: int = None
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        if timestamp_awaiting_finalization:
            transaction.timestamp_awaiting_finalization = (
                timestamp_awaiting_finalization
            )
        else:
            transaction.timestamp_awaiting_finalization = int(time.time())

    def set_transaction_appeal_failed(self, transaction_hash: str, appeal_failed: int):
        if appeal_failed < 0:
            raise ValueError("appeal_failed must be a non-negative integer")
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appeal_failed = appeal_failed

    def set_transaction_appeal_undetermined(
        self, transaction_hash: str, appeal_undetermined: bool
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appeal_undetermined = appeal_undetermined

    def get_highest_timestamp(self) -> int:
        transaction = (
            self.session.query(Transactions)
            .filter(Transactions.timestamp_awaiting_finalization.isnot(None))
            .order_by(desc(Transactions.timestamp_awaiting_finalization))
            .first()
        )
        if transaction is None:
            return 0
        return transaction.timestamp_awaiting_finalization

    def get_transactions_for_block(
        self, block_number: int, include_full_tx: bool
    ) -> dict:
        transactions = (
            self.session.query(Transactions)
            .filter(Transactions.timestamp_awaiting_finalization == block_number)
            .all()
        )

        block_hash = "0x" + "0" * 64
        parent_hash = "0x" + "0" * 64  # Placeholder for parent block hash
        timestamp = (
            transactions[0].timestamp_awaiting_finalization
            if len(transactions) > 0
            else int(time.time())
        )

        if include_full_tx:
            transaction_data = [self._parse_transaction_data(tx) for tx in transactions]
        else:
            transaction_data = [tx.hash for tx in transactions]

        block_details = {
            "number": hex(block_number),
            "hash": block_hash,
            "parentHash": parent_hash,
            "nonce": "0x" + "0" * 16,
            "transactions": transaction_data,
            "timestamp": hex(int(timestamp)),
            "miner": "0x" + "0" * 40,
            "difficulty": "0x1",
            "gasUsed": "0x0",
            "gasLimit": "0x0",
            "size": "0x0",
            "extraData": "0x",
        }

        return block_details

    def get_newer_transactions(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transactions = (
            self.session.query(Transactions)
            .filter(
                Transactions.created_at > transaction.created_at,
                Transactions.to_address == transaction.to_address,
            )
            .order_by(Transactions.created_at)
            .all()
        )
        return [
            self._parse_transaction_data(transaction) for transaction in transactions
        ]

    def update_consensus_history(
        self,
        transaction_hash: str,
        consensus_round: str,
        leader_result: list[Receipt] | None,
        validator_results: list[Receipt],
        extra_status_change: TransactionStatus | None = None,
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )

        status_changes_to_use = (
            transaction.consensus_history["current_status_changes"]
            if "current_status_changes" in transaction.consensus_history
            else []
        )
        if extra_status_change:
            status_changes_to_use.append(extra_status_change.value)

        current_consensus_results = {
            "consensus_round": consensus_round,
            "leader_result": (
                [receipt.to_dict() for receipt in leader_result]
                if leader_result
                else None
            ),
            "validator_results": [receipt.to_dict() for receipt in validator_results],
            "status_changes": status_changes_to_use,
        }

        if "consensus_results" in transaction.consensus_history:
            transaction.consensus_history["consensus_results"].append(
                current_consensus_results
            )
        else:
            transaction.consensus_history["consensus_results"] = [
                current_consensus_results
            ]

        transaction.consensus_history["current_status_changes"] = []

        flag_modified(transaction, "consensus_history")
        self.session.commit()

    def reset_consensus_history(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.consensus_history = {}
        self.session.commit()

    def set_transaction_timestamp_appeal(
        self, transaction: Transactions | str, timestamp_appeal: int | None
    ):
        if isinstance(transaction, str):  # hash
            transaction = (
                self.session.query(Transactions).filter_by(hash=transaction).one()
            )
        transaction.timestamp_appeal = timestamp_appeal

    def set_transaction_appeal_processing_time(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appeal_processing_time += (
            round(time.time()) - transaction.timestamp_appeal
        )
        flag_modified(transaction, "appeal_processing_time")
        self.session.commit()

    def reset_transaction_appeal_processing_time(self, transaction_hash: str):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.appeal_processing_time = 0
        self.session.commit()

    def set_transaction_contract_snapshot(
        self, transaction_hash: str, contract_snapshot: dict | None
    ):
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.contract_snapshot = contract_snapshot
        self.session.commit()

    def transactions_in_process_by_contract(self) -> list[dict]:
        transactions = (
            self.session.query(Transactions)
            .filter(
                Transactions.to_address.isnot(None),
                Transactions.status.in_(
                    [
                        TransactionStatus.ACTIVATED,
                        TransactionStatus.PROPOSING,
                        TransactionStatus.COMMITTING,
                        TransactionStatus.REVEALING,
                    ]
                ),
            )
            .distinct(Transactions.to_address)
            .order_by(Transactions.to_address, Transactions.created_at.asc())
            .all()
        )

        return [
            self._parse_transaction_data(transaction) for transaction in transactions
        ]

    def get_previous_transaction(
        self, transaction_hash: str, status: TransactionStatus | None = None
    ) -> dict | None:
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )

        if transaction.type == TransactionType.DEPLOY_CONTRACT:
            return None

        filters = [
            Transactions.created_at < transaction.created_at,
            Transactions.to_address == transaction.to_address,
        ]
        if status is not None:
            filters.append(Transactions.status == status)

        closest_transaction = (
            self.session.query(Transactions)
            .filter(*filters)
            .order_by(desc(Transactions.created_at))
            .first()
        )

        return (
            self._parse_transaction_data(closest_transaction)
            if closest_transaction
            else None
        )

    def set_transaction_timestamp_last_vote(self, transaction_hash: str):
        """
        Set the last vote timestamp for a transaction to the current time.

        Args:
            transaction_hash: The hash of the transaction to update

        Raises:
            NoResultFound: If the transaction with the given hash doesn't exist
        """
        transaction = (
            self.session.query(Transactions).filter_by(hash=transaction_hash).one()
        )
        transaction.last_vote_timestamp = int(time.time())
        self.session.commit()

    def increase_transaction_rotation_count(self, transaction_hash: str):
        """
        Increment the rotation count for a transaction by 1.

        Args:
            transaction_hash: The hash of the transaction to update

        Raises:
            NoResultFound: If the transaction with the given hash doesn't exist
        """
        transaction = (
            self.session.query(Transactions)
            .filter_by(hash=transaction_hash)
            .with_for_update()  # lock row
            .one()
        )
        max_rotations = transaction.config_rotation_rounds or 0
        if max_rotations and transaction.rotation_count >= max_rotations:
            self.session.commit()
            return  # already at the ceiling
        transaction.rotation_count += 1
        flag_modified(transaction, "rotation_count")
        self.session.commit()

    def reset_transaction_rotation_count(self, transaction_hash: str):
        """
        Reset the rotation count for a transaction to 0.

        Args:
            transaction_hash: The hash of the transaction to update

        Raises:
            NoResultFound: If the transaction with the given hash doesn't exist
        """
        transaction = (
            self.session.query(Transactions)
            .filter_by(hash=transaction_hash)
            .with_for_update()  # Add row-level locking
            .one()
        )
        transaction.rotation_count = 0
        self.session.commit()
