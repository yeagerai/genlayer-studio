# tests/e2e/test_storage.py
from tests.common.request import (
    deploy_intelligent_contract,
    send_transaction,
    payload,
    post_request_localhost,
)

from tests.integration.contract_examples.mocks.user_storage_get_contract_schema_for_code import (
    user_storage_contract_schema,
)
from tests.integration.contract_examples.mocks.call_contract_function import (
    call_contract_function_response,
)

from tests.common.response import (
    assert_dict_struct,
    assert_dict_exact,
    has_success_status,
)

from tests.common.accounts import create_new_account
from tests.common.request import call_contract_method

import json
from backend.node.types import Address

INITIAL_STATE_USER_A = "user_a_initial_state"
UPDATED_STATE_USER_A = "user_a_updated_state"
INITIAL_STATE_USER_B = "user_b_initial_state"
UPDATED_STATE_USER_B = "user_b_updated_state"


def test_user_storage(setup_validators):
    # Account Setup
    from_account_a = create_new_account()
    from_account_b = create_new_account()

    # Get contract schema
    contract_code = open("examples/contracts/user_storage.py", "r").read()
    result_schema = post_request_localhost(
        payload("gen_getContractSchemaForCode", contract_code)
    ).json()
    assert has_success_status(result_schema)
    assert_dict_exact(result_schema, user_storage_contract_schema)

    # Deploy Contract
    # Deploy Contract
    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account_a, contract_code, []
    )

    assert has_success_status(transaction_response_deploy)

    ########################################
    ######### GET Initial State ############
    ########################################
    contract_state_1 = call_contract_method(
        contract_address, from_account_a, "get_complete_storage", []
    )
    assert contract_state_1 == {}

    ########################################
    ########## ADD User A State ############
    ########################################
    transaction_response_call_1 = send_transaction(
        from_account_a, contract_address, "update_storage", [INITIAL_STATE_USER_A]
    )
    assert has_success_status(transaction_response_call_1)

    # Assert response format
    assert_dict_struct(transaction_response_call_1, call_contract_function_response)

    # Get Updated State
    contract_state_2_1 = call_contract_method(
        contract_address, from_account_a, "get_complete_storage", []
    )
    print(contract_state_2_1)
    assert contract_state_2_1[from_account_a.address] == INITIAL_STATE_USER_A

    # Get Updated State
    contract_state_2_2 = call_contract_method(
        contract_address,
        from_account_a,
        "get_account_storage",
        [from_account_a.address],
    )
    assert contract_state_2_2 == INITIAL_STATE_USER_A

    ########################################
    ########## ADD User B State ############
    ########################################
    transaction_response_call_2 = send_transaction(
        from_account_b, contract_address, "update_storage", [INITIAL_STATE_USER_B]
    )
    assert has_success_status(transaction_response_call_2)

    # Assert response format
    assert_dict_struct(transaction_response_call_2, call_contract_function_response)

    # Get Updated State
    contract_state_3 = call_contract_method(
        contract_address, from_account_a, "get_complete_storage", []
    )
    assert contract_state_3[from_account_a.address] == INITIAL_STATE_USER_A
    assert contract_state_3[from_account_b.address] == INITIAL_STATE_USER_B

    #########################################
    ######### UPDATE User A State ###########
    #########################################
    transaction_response_call_3 = send_transaction(
        from_account_a, contract_address, "update_storage", [UPDATED_STATE_USER_A]
    )
    assert has_success_status(transaction_response_call_3)

    # Assert response format
    assert_dict_struct(transaction_response_call_3, call_contract_function_response)

    # Get Updated State
    contract_state_4_1 = call_contract_method(
        contract_address, from_account_a, "get_complete_storage", []
    )
    assert contract_state_4_1[from_account_a.address] == UPDATED_STATE_USER_A
    assert contract_state_4_1[from_account_b.address] == INITIAL_STATE_USER_B

    # Get Updated State
    contract_state_4_2 = call_contract_method(
        contract_address,
        from_account_a,
        "get_account_storage",
        [from_account_b.address],
    )
    assert contract_state_4_2 == INITIAL_STATE_USER_B
