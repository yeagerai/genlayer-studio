import os
import json
import asyncio
import uuid
from flask import Flask
from flask_jsonrpc import JSONRPC

from database.init_db import create_db_if_doesnt_already_exists, create_tables_in_db
from database.credentials import get_genlayer_db_connection
from consensus.algorithm import exec_transaction

from dotenv import load_dotenv
load_dotenv()

# TODO: Do we need logging?
app = Flask('jsonrpc_api')
jsonrpc = JSONRPC(app, "/api", enable_web_browsable_api=True)


@jsonrpc.method("create_db")
def create_db() -> dict:
    result = create_db_if_doesnt_already_exists()
    app.logger.info(result)
    return {"status": result}

@jsonrpc.method("create_tables")
def create_tables() -> dict:
    result = create_tables_in_db(app)
    app.logger.info(result)
    return {"status": result}


@jsonrpc.method("create_new_EOA")
def create_new_eoa(balance: float) -> dict:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()
    new_eoa_id = str(uuid.uuid4())  # Generate a unique ID for the new EOA
    account_state = json.dumps({"balance": balance})

    # Update current_state table with the new account and its balance
    cursor.execute(
        "INSERT INTO current_state (id, state) VALUES (%s, %s);",
        (new_eoa_id, account_state),
    )

    # Optionally log the account creation in the transactions table
    cursor.execute(
        "INSERT INTO transactions (from_address, to_address, data, value, type) VALUES (NULL, %s, %s, %s, 0);",
        (
            new_eoa_id,
            json.dumps({"action": "create_account", "initial_balance": balance}),
            balance,
        ),
    )

    connection.commit()
    cursor.close()
    connection.close()
    return {"id": new_eoa_id, "balance": balance, "status": "EOA created"}


@jsonrpc.method("send_transaction")
def send_transaction(from_account: str, to_account: str, amount: float) -> dict:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()

    # Verify sender's balance
    cursor.execute("SELECT state FROM current_state WHERE id = %s;", (from_account,))
    sender_state = cursor.fetchone()
    if sender_state and sender_state[0].get("balance", 0) >= amount:
        # Update sender's balance
        new_sender_balance = sender_state[0]["balance"] - amount
        cursor.execute(
            "UPDATE current_state SET state = jsonb_set(state, '{balance}', %s) WHERE id = %s;",
            (json.dumps(new_sender_balance), from_account),
        )

        # Update recipient's balance
        cursor.execute("SELECT state FROM current_state WHERE id = %s;", (to_account,))
        recipient_state = cursor.fetchone()
        if recipient_state:
            new_recipient_balance = recipient_state[0].get("balance", 0) + amount
            cursor.execute(
                "UPDATE current_state SET state = jsonb_set(state, '{balance}', %s) WHERE id = %s;",
                (json.dumps(new_recipient_balance), to_account),
            )
        else:
            # Create account if it doesn't exist
            cursor.execute(
                "INSERT INTO current_state (id, state) VALUES (%s, %s);",
                (to_account, json.dumps({"balance": amount})),
            )

        # Log the transaction
        cursor.execute(
            "INSERT INTO transactions (from_address, to_address, data, value, type) VALUES (%s, %s, %s, %s, 0);",
            (from_account, to_account, json.dumps({"amount": amount}), amount),
        )
        connection.commit()
        status = "success"
    else:
        status = "failure: insufficient funds"

    cursor.close()
    connection.close()
    return {"status": status}


@jsonrpc.method("deploy_intelligent_contract")
def deploy_intelligent_contract(from_account: str, contract_code: str, initial_state: dict) -> dict:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()
    contract_id = str(uuid.uuid4())
    return {"status": "deployed", "contract_id": "something"}

    cursor.execute(
        "INSERT INTO current_state (id, state) VALUES (%s, %s);",
        (contract_id, json.dumps({"code": contract_code, "state": initial_state})),
    )

    cursor.execute(
        "INSERT INTO transactions (from_address, to_address, data, type) VALUES (%s, %s, %s, 1);",
        (from_account, contract_id, json.dumps({"contract_code": contract_code})),
    )

    connection.commit()
    cursor.close()
    connection.close()
    return {"status": "deployed", "contract_id": contract_id}


@jsonrpc.method("register_validator")
def register_validator(stake: float) -> dict:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()

    eoa_id = str(uuid.uuid4())
    eoa_state = json.dumps({"staked_balance": stake})

    cursor.execute(
        "INSERT INTO current_state (id, state) VALUES (%s, %s);", (eoa_id, eoa_state)
    )

    validator_info = json.dumps({"eoa_id": eoa_id, "stake": stake})
    cursor.execute(
        "INSERT INTO validators (stake, validator_info) VALUES (%s, %s);",
        (stake, validator_info),
    )

    connection.commit()
    cursor.close()
    connection.close()
    return {"validator_id": eoa_id, "stake": stake, "status": "registered"}


@jsonrpc.method("call_contract_function")
async def call_contract_function(
    from_account: str, contract_address: str, function_name: str, args: list
) -> dict:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()

    function_call_data = json.dumps(
        {"function": function_name, "args": args, "contract_address": contract_address}
    )

    cursor.execute(
        "INSERT INTO transactions (from_address, to_address, data, type, created_at, final) VALUES (%s, %s, %s, 2, CURRENT_TIMESTAMP, %s);",
        (from_account, contract_address, function_call_data, False),
    )

    connection.commit()

    # call consensus
    asyncio.create_task(exec_transaction(json.loads(function_call_data)))

    cursor.close()
    connection.close()
    return {
        "status": "success",
        "message": f"Function '{function_name}' called on contract at {contract_address} with args {args}.",
    }

@jsonrpc.method("get_last_contracts")
def get_last_contracts(number_of_contracts: int) -> list:
    connection = get_genlayer_db_connection()
    cursor = connection.cursor()

    # Query the database for the last N deployed contracts
    cursor.execute(
        "SELECT to_address, data FROM transactions WHERE type = 1 ORDER BY created_at DESC LIMIT %s;",
        (number_of_contracts,)
    )
    contracts = cursor.fetchall()

    # Format the result
    contracts_info = []
    for contract in contracts:
        contract_info = {
            "contract_id": contract[0]
        }
        contracts_info.append(contract_info)

    cursor.close()
    connection.close()

    return contracts_info

if __name__ == "__main__":
    app.run(debug=True, port=os.environ['RPCPORT'], host='0.0.0.0')
