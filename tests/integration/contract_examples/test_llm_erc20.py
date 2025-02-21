# tests/e2e/test_storage.py
import eth_utils

from backend.node.types import Address
from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    payload,
    post_request_localhost,
)
from tests.integration.contract_examples.mocks.llm_erc20_get_contract_schema_for_code import (
    llm_erc20_contract_schema,
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

from tests.integration.conftest import (
    setup_mock_validators,
    cleanup_mock_validators,
    get_prompts_from_contract_code,
)

TOKEN_TOTAL_SUPPLY = 1000
TRANSFER_AMOUNT = 100


def test_llm_erc20():
    try:
        # Account Setup
        from_account_a = create_new_account()
        from_account_b = create_new_account()

        # Get contract schema
        contract_code = open("examples/contracts/llm_erc20.py", "r").read()

        # Parse prompts from contract code
        prompts = get_prompts_from_contract_code(contract_code)

        # Mock the validator responses
        responses = {
            prompts[1]: {
                "transaction_success": True,
                "transaction_error": "",
                "updated_balances": {
                    from_account_a.address: 900,
                    from_account_b.address: 100,
                },
            },
        }

        setup_mock_validators(responses)

        result_schema = post_request_localhost(
            payload(
                "gen_getContractSchemaForCode",
                eth_utils.hexadecimal.encode_hex(contract_code),
            )
        ).json()
        assert has_success_status(result_schema)
        assert_dict_exact(result_schema, llm_erc20_contract_schema)

        # Deploy Contract
        contract_address, transaction_response_deploy = deploy_intelligent_contract(
            from_account_a, contract_code, [TOKEN_TOTAL_SUPPLY]
        )

        assert has_success_status(transaction_response_deploy)

        ########################################
        ######### GET Initial State ############
        ########################################
        contract_state_1 = call_contract_method(
            contract_address, from_account_a, "get_balances", []
        )
        assert contract_state_1[from_account_a.address] == TOKEN_TOTAL_SUPPLY

        ########################################
        #### TRANSFER from User A to User B ####
        ########################################
        transaction_response_call_1 = write_intelligent_contract(
            from_account_a,
            contract_address,
            "transfer",
            [TRANSFER_AMOUNT, from_account_b.address],
        )
        assert has_success_status(transaction_response_call_1)

        # Assert response format
        assert_dict_struct(transaction_response_call_1, call_contract_function_response)

        # Get Updated State
        contract_state_2_1 = call_contract_method(
            contract_address, from_account_a, "get_balances", []
        )
        assert has_success_status(contract_state_2_1)
        assert (
            contract_state_2_1[from_account_a.address]
            == TOKEN_TOTAL_SUPPLY - TRANSFER_AMOUNT
        )

        assert contract_state_2_1[from_account_b.address] == TRANSFER_AMOUNT

        # Get Updated State
        contract_state_2_2 = call_contract_method(
            contract_address, from_account_a, "get_balance_of", [from_account_a.address]
        )
        assert contract_state_2_2 == TOKEN_TOTAL_SUPPLY - TRANSFER_AMOUNT

        # Get Updated State
        contract_state_2_3 = call_contract_method(
            contract_address, from_account_a, "get_balance_of", [from_account_b.address]
        )
        assert contract_state_2_3 == TRANSFER_AMOUNT

    finally:
        cleanup_mock_validators()
