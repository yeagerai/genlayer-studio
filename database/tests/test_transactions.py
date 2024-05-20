import re
import psycopg2

from common.testing.db.base import transaction_data
from common.testing.db.base import setup_db_and_tables
from database.functions import DatabaseFunctions


def test_insert_transaction():
    setup_db_and_tables()
    random_transaction_data = transaction_data()
    with DatabaseFunctions() as dbf:
        transaction = dbf.insert_transaction(**random_transaction_data)
        dbf.close()

    assert transaction["from_address"] == random_transaction_data["from_address"]
    assert transaction["to_address"] == transaction_data()["to_address"]
    assert transaction["data"] == transaction_data()["data"]
    assert transaction["input_data"] == transaction_data()["input_data"]
    assert transaction["consensus_data"] == transaction_data()["consensus_data"]
    assert transaction["nonce"] == transaction_data()["nonce"]
    assert transaction["value"] == transaction_data()["value"]
    assert transaction["type"] == transaction_data()["type"]
    assert transaction["status"] == transaction_data()["status"]
    assert transaction["gaslimit"] == transaction_data()["gaslimit"]
    assert transaction["r"] == transaction_data()["r"]
    assert transaction["s"] == transaction_data()["s"]
    assert transaction["v"] == transaction_data()["v"]
    assert re.match(r"\d{2}/\d{2}/\d{4} \d{1,2}:\d{2}:\d{2}", transaction["created_at"])


def test_insert_transaction_for_status_that_does_not_exist():
    setup_db_and_tables()
    random_transaction_data = transaction_data()
    random_transaction_data["status"] = "this is not a status"
    try:
        with DatabaseFunctions() as dbf:
            dbf.insert_transaction(**random_transaction_data)
            dbf.close()
        assert False
    except psycopg2.errors.CheckViolation:
        assert True


# TODO: This
def test_get_transaction_for_address_that_doesnt_exist():
    pass


def test_get_transaction_for_transacttion_that_does_not_exist():
    setup_db_and_tables()
    random_transaction_data = transaction_data()
    with DatabaseFunctions() as dbf:
        dbf.insert_transaction(**random_transaction_data)
        get_transaction_result = dbf.get_transaction(2)
        dbf.close()

    assert get_transaction_result is None


def test_get_transaction():
    setup_db_and_tables()
    random_transaction_data = transaction_data()
    with DatabaseFunctions() as dbf:
        transaction_insert_result = dbf.insert_transaction(**random_transaction_data)
        transaction = dbf.get_transaction(transaction_insert_result["id"])
        dbf.close()

    assert transaction["from_address"] == random_transaction_data["from_address"]
    assert transaction["to_address"] == transaction_data()["to_address"]
    assert transaction["data"] == transaction_data()["data"]
    assert transaction["input_data"] == transaction_data()["input_data"]
    assert transaction["consensus_data"] == transaction_data()["consensus_data"]
    assert transaction["nonce"] == transaction_data()["nonce"]
    assert transaction["value"] == transaction_data()["value"]
    assert transaction["type"] == transaction_data()["type"]
    assert transaction["status"] == transaction_data()["status"]
    assert transaction["gaslimit"] == transaction_data()["gaslimit"]
    assert transaction["r"] == transaction_data()["r"]
    assert transaction["s"] == transaction_data()["s"]
    assert transaction["v"] == transaction_data()["v"]
    assert re.match(r"\d{2}/\d{2}/\d{4} \d{1,2}:\d{2}:\d{2}", transaction["created_at"])