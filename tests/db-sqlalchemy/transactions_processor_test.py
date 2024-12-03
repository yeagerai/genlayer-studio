import math
from datetime import datetime

from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)


def test_transactions_processor(transactions_processor: TransactionsProcessor):

    from_address = "0x9F0e84243496AcFB3Cd99D02eA59673c05901501"
    to_address = "0xAcec3A6d871C25F591aBd4fC24054e524BBbF794"
    data = {"key": "value"}
    value = 2.0
    transaction_type = 1
    nonce = 0

    # Used to test the triggered_by field
    first_transaction_hash = transactions_processor.insert_transaction(
        from_address,
        to_address,
        data,
        value,
        transaction_type,
        nonce,
        True,
        None,
    )
    transactions_processor.session.commit()

    actual_transaction_hash = transactions_processor.insert_transaction(
        from_address,
        to_address,
        data,
        value,
        transaction_type,
        nonce + 1,
        True,
        None,
        first_transaction_hash,
    )

    actual_transaction = transactions_processor.get_transaction_by_hash(
        actual_transaction_hash
    )

    assert actual_transaction["from_address"] == from_address
    assert actual_transaction["to_address"] == to_address
    assert actual_transaction["data"] == data
    assert math.isclose(actual_transaction["value"], value)
    assert actual_transaction["type"] == transaction_type
    assert actual_transaction["status"] == TransactionStatus.PENDING.value
    assert actual_transaction["hash"] == actual_transaction_hash
    created_at = actual_transaction["created_at"]
    assert datetime.fromisoformat(created_at)
    assert actual_transaction["leader_only"] is True
    assert actual_transaction["triggered_by"] == first_transaction_hash
    new_status = TransactionStatus.ACCEPTED
    transactions_processor.update_transaction_status(
        actual_transaction_hash, new_status
    )

    actual_transaction = transactions_processor.get_transaction_by_hash(
        actual_transaction_hash
    )

    assert actual_transaction["status"] == new_status.value
    assert actual_transaction["hash"] == actual_transaction_hash
    assert actual_transaction["from_address"] == from_address
    assert actual_transaction["to_address"] == to_address
    assert actual_transaction["data"] == data
    assert math.isclose(actual_transaction["value"], value)
    assert actual_transaction["type"] == transaction_type
    assert actual_transaction["created_at"] == created_at
    assert actual_transaction["leader_only"] is True

    consensus_data = {"result": "success"}
    transactions_processor.set_transaction_result(
        actual_transaction_hash, consensus_data
    )

    new_status = TransactionStatus.FINALIZED
    transactions_processor.update_transaction_status(
        actual_transaction_hash, new_status
    )

    actual_transaction = transactions_processor.get_transaction_by_hash(
        actual_transaction_hash
    )

    assert actual_transaction["status"] == TransactionStatus.FINALIZED.value
    assert actual_transaction["consensus_data"] == consensus_data
    assert actual_transaction["hash"] == actual_transaction_hash
    assert actual_transaction["from_address"] == from_address
    assert actual_transaction["to_address"] == to_address
    assert actual_transaction["data"] == data
    assert math.isclose(actual_transaction["value"], value)
    assert actual_transaction["type"] == transaction_type
    assert actual_transaction["created_at"] == created_at
