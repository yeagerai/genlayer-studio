# rpc/transaction_utils.py

import rlp
from rlp.sedes import text, binary
from rlp.exceptions import DeserializationError, SerializationError
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction, vrs_from
from eth_account._utils.signing import hash_of_signed_transaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from backend.protocol_rpc.types import (
    DecodedDeploymentData,
    DecodedMethodCallData,
    DecodedTransaction,
)


class Boolean:
    """A sedes for booleans
    Copied from rlp/sedes/boolean.py
    Adding custom logic to also handle `False` as `0x00`, since the Frontend library sends `False` as `0x00`
    """

    def serialize(self, obj):
        if not isinstance(obj, bool):
            raise SerializationError("Can only serialize integers", obj)

        if obj is False:
            return b""
        elif obj is True:
            return b"\x01"
        else:
            raise Exception("Invariant: no other options for boolean values")

    def deserialize(self, serial):
        if serial == b"":
            return False
        elif serial == b"\x01":
            return True
        elif serial == b"\x00":  # Custom logic to handle `False` as `0x00`
            return False
        else:
            raise DeserializationError(
                "Invalid serialized boolean.  Must be either 0x01 or 0x00", serial
            )


boolean = Boolean()


def decode_signed_transaction(raw_transaction: str) -> DecodedTransaction | None:
    try:
        transaction_bytes = HexBytes(raw_transaction)
        signed_transaction = Transaction.from_bytes(transaction_bytes)
        msg_hash = hash_of_signed_transaction(signed_transaction)
        vrs = vrs_from(signed_transaction)

        # extracting sender address
        sender = Account._recover_hash(msg_hash, vrs=vrs)
        signed_transaction_as_dict = signed_transaction.as_dict()
        to_address = (
            to_checksum_address(f"0x{signed_transaction_as_dict['to'].hex()}")
            if signed_transaction_as_dict["to"]
            else None
        )
        nonce = signed_transaction_as_dict["nonce"]
        value = signed_transaction_as_dict["value"]
        data = (
            signed_transaction_as_dict["data"].hex()
            if signed_transaction_as_dict["data"]
            else None
        )
        return DecodedTransaction(
            from_address=sender,
            to_address=to_address,
            data=data,
            type=signed_transaction_as_dict.get("type", 0),
            nonce=nonce,
            value=value,
        )

    except Exception as e:
        print("Error decoding transaction", e)
        return None


def transaction_has_valid_signature(
    raw_transaction: str, decoded_tx: DecodedTransaction
) -> bool:
    recovered_address = Account.recover_transaction(raw_transaction)
    # Compare the recovered address with the 'from' address in the transaction
    return recovered_address == decoded_tx.from_address


def decode_method_call_data(data: str) -> DecodedMethodCallData:
    data_bytes = HexBytes(data)

    try:
        data_decoded = rlp.decode(data_bytes, MethodCallTransactionPayload)
    except rlp.exceptions.DeserializationError as e:
        print("WARN | falling back to default decode method call data:", e)
        data_decoded = rlp.decode(data_bytes, MethodCallTransactionPayloadDefault)

    leader_only = getattr(data_decoded, "leader_only", False)

    return DecodedMethodCallData(
        calldata=data_decoded["calldata"],
        leader_only=leader_only,
    )


def decode_deployment_data(data: str) -> DecodedDeploymentData:
    data_bytes = HexBytes(data)

    try:
        data_decoded = rlp.decode(data_bytes, DeploymentContractTransactionPayload)
    except rlp.exceptions.DeserializationError as e:
        print("Error decoding deployment data, falling back to default:", e)
        data_decoded = rlp.decode(
            data_bytes, DeploymentContractTransactionPayloadDefault
        )

    leader_only = getattr(data_decoded, "leader_only", False)

    return DecodedDeploymentData(
        contract_code=data_decoded["contract_code"],
        calldata=data_decoded["calldata"],
        leader_only=leader_only,
    )


class DeploymentContractTransactionPayload(rlp.Serializable):
    fields = [
        ("contract_code", binary),
        ("calldata", binary),
        ("leader_only", boolean),
    ]


class DeploymentContractTransactionPayloadDefault(rlp.Serializable):
    fields = [
        ("contract_code", binary),
        ("calldata", binary),
    ]


class MethodCallTransactionPayload(rlp.Serializable):
    fields = [
        ("calldata", binary),
        ("leader_only", boolean),
    ]


class MethodCallTransactionPayloadDefault(rlp.Serializable):
    fields = [
        ("calldata", binary),
    ]
