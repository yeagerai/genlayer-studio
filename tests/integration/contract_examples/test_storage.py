# tests/e2e/test_storage.py
from tests.common.request import (
    deploy_intelligent_contract,
    send_transaction,
    payload,
    post_request_localhost,
)
from tests.integration.contract_examples.mocks.storage_get_contract_schema_for_code import (
    storage_contract_schema,
)
from tests.integration.contract_examples.mocks.call_contract_function import (
    call_contract_function_response,
)

from tests.common.response import (
    assert_dict_struct,
    assert_dict_exact,
    has_success_status,
)

from tests.common.request import call_contract_method

import json

INITIAL_STATE = "a"
UPDATED_STATE = "b"


def test_storage(setup_validators, from_account):
    # Get contract schema
    contract_code = open("examples/contracts/storage.py", "r").read()
    result_schema = post_request_localhost(
        payload("gen_getContractSchemaForCode", contract_code)
    ).json()
    assert has_success_status(result_schema)
    assert_dict_exact(result_schema, storage_contract_schema)

    # Deploy Contract
    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account, contract_code, [INITIAL_STATE]
    )

    assert has_success_status(transaction_response_deploy)

    # Get Initial State
    contract_state_1 = call_contract_method(
        contract_address, from_account, "get_storage", []
    )
    assert contract_state_1 == INITIAL_STATE

    # Update State
    transaction_response_call_1 = send_transaction(
        from_account, contract_address, "update_storage", [UPDATED_STATE]
    )

    assert has_success_status(transaction_response_call_1)
    print("transaction_response_call_1", transaction_response_call_1)
    # Assert response format
    assert_dict_struct(transaction_response_call_1, call_contract_function_response)

    # Get Updated State
    contract_state_2 = call_contract_method(
        contract_address, from_account, "get_storage", []
    )
    assert contract_state_2 == UPDATED_STATE
