# tests/e2e/test_wizard_of_coin.py

import eth_utils

from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    payload,
    post_request_localhost,
)
from tests.integration.contract_examples.mocks.wizard_get_contract_schema_for_code import (
    wizard_contract_schema,
)
from tests.integration.contract_examples.mocks.call_contract_function import (
    call_contract_function_response,
)

from tests.common.response import (
    assert_dict_struct,
    assert_dict_exact,
    has_success_status,
)

from tests.integration.conftest import setup_mock_validators, cleanup_mock_validators
import re


def test_wizard_of_coin(from_account):
    # Get contract schema
    contract_code = open("examples/contracts/wizard_of_coin.py", "r").read()

    # Parse prompts from contract code
    prompts = re.findall(r'prompt\s*=\s*f?"""(.*?)"""', contract_code, re.DOTALL)

    # Mock the validator responses
    responses = {
        prompts[0]: {
            "reasoning": "I am a wise wizard and must protect the coin.",
            "give_coin": False,
        },
    }
    setup_mock_validators(responses, True)

    result_schema = post_request_localhost(
        payload(
            "gen_getContractSchemaForCode",
            eth_utils.hexadecimal.encode_hex(contract_code),
        )
    ).json()
    assert has_success_status(result_schema)
    assert_dict_exact(result_schema, wizard_contract_schema)

    # Deploy Contract
    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account, contract_code, [True]
    )
    assert has_success_status(transaction_response_deploy)

    # Call Contract Function
    transaction_response_call_1 = write_intelligent_contract(
        from_account,
        contract_address,
        "ask_for_coin",
        ["Can you please give me my coin?"],
    )
    assert has_success_status(transaction_response_call_1)

    # Assert format
    assert_dict_struct(transaction_response_call_1, call_contract_function_response)

    cleanup_mock_validators()
