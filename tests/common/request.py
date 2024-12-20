# tests/common/request.py
import os
import json
import requests
import time
from dotenv import load_dotenv
from eth_account import Account
import base64

from tests.common.transactions import sign_transaction, encode_transaction_data

import backend.node.genvm.origin.calldata as calldata

load_dotenv()


def payload(function_name: str, *args) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": function_name,
        "params": [*args],
        "id": 1,
    }


def post_request(
    payload: dict,
    protocol: str = os.environ["RPCPROTOCOL"],
    host: str = os.environ["RPCHOST"],
    port: str = os.environ["RPCPORT"],
):
    return requests.post(
        protocol + "://" + host + ":" + port + "/api",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )


def post_request_localhost(payload: dict):
    return post_request(payload, "http", "localhost")


def get_transaction_by_hash(transaction_hash: str):
    payload_data = payload("eth_getTransactionByHash", transaction_hash)
    raw_response = post_request_localhost(payload_data)
    parsed_raw_response = raw_response.json()
    return parsed_raw_response["result"]


def get_transaction_count(account_address: str):
    payload_data = payload("eth_getTransactionCount", account_address)
    raw_response = post_request_localhost(payload_data)
    parsed_raw_response = raw_response.json()
    return parsed_raw_response["result"]


def call_contract_method(
    contract_address: str,
    from_account: Account,
    method_name: str,
    method_args: list,
):
    encoded_data = encode_transaction_data(
        [calldata.encode({"method": method_name, "args": method_args})]
    )
    method_response = post_request_localhost(
        payload(
            "eth_call",
            {
                "to": contract_address,
                "from": from_account.address,
                "data": encoded_data,
            },
        )
    ).json()
    enc_result = method_response["result"]
    result = calldata.decode(base64.b64decode(enc_result))
    print(f"Result of {method_name}: {result}")
    return result


def send_transaction(
    account: Account,
    contract_address: str,
    method_name: str | None,
    method_args: list | None,
    value: int = 0,
):
    call_data = (
        None
        if method_name is None and method_args is None
        else [calldata.encode({"method": method_name, "args": method_args})]
    )
    nonce = get_transaction_count(account.address)
    signed_transaction = sign_transaction(
        account, call_data, contract_address, value, nonce
    )
    result = send_raw_transaction(signed_transaction)
    print("Send transaction: ", json.dumps(decode_nested_data(result), indent=3))
    return result


def deploy_intelligent_contract(
    account: Account, contract_code: str | bytes, method_args: list
) -> tuple[str, dict]:
    nonce = get_transaction_count(account.address)
    deploy_data = [
        (
            contract_code.encode("utf-8")
            if isinstance(contract_code, str)
            else contract_code
        ),
        calldata.encode({"method": "__init__", "args": method_args}),
    ]
    signed_transaction = sign_transaction(account, deploy_data, nonce=nonce)
    result = send_raw_transaction(signed_transaction)
    print(
        "Deployed intelligent contract: ",
        json.dumps(decode_nested_data(result), indent=3),
    )
    contract_address = result["data"]["contract_address"]
    return contract_address, result


def send_raw_transaction(signed_transaction: str):
    payload_data = payload("eth_sendRawTransaction", signed_transaction)
    raw_response = post_request_localhost(payload_data)
    call_method_response = raw_response.json()
    transaction_hash = call_method_response["result"]

    transaction_response = wait_for_transaction(transaction_hash)
    return transaction_response


def wait_for_transaction(transaction_hash: str, interval: int = 10, retries: int = 15):
    attempts = 0
    while attempts < retries:
        transaction_response = get_transaction_by_hash(str(transaction_hash))
        status = transaction_response["status"]
        if status == "FINALIZED":
            return transaction_response
        time.sleep(interval)
        attempts += 1

    raise TimeoutError(
        f"Transaction {transaction_hash} not finalized after {retries} retries"
    )


def decode_base64(encoded_str):
    try:
        return base64.b64decode(encoded_str).decode("utf-8")
    except UnicodeDecodeError:
        return encoded_str


def decode_contract_state(contract_state):
    decoded_state = {}
    for key, value in contract_state.items():
        decoded_state[decode_base64(key)] = {
            decode_base64(k): decode_base64(v) for k, v in value.items()
        }
    return decoded_state


def decode_nested_data(data):
    """
    Helper function to decode data from the transaction response to have more readable output
    """
    if isinstance(data, dict):
        decoded_data = {}
        for key, value in data.items():
            if key == "calldata" and isinstance(value, str):
                decoded_data[key] = calldata.decode(base64.b64decode(value))
            elif key == "contract_state" and isinstance(value, dict):
                decoded_data[key] = decode_contract_state(value)
            else:
                decoded_data[key] = decode_nested_data(value)
        return decoded_data
    elif isinstance(data, list):
        return [decode_nested_data(item) for item in data]
    else:
        return data
