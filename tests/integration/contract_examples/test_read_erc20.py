import json
import os

from tests.common.request import (
    call_contract_method,
    deploy_intelligent_contract,
)
from tests.common.response import has_success_status


def test_read_erc20(setup_validators, from_account):
    """
    Tests that recursive contract calls work by:
    1. creating an LLM ERC20 contract
    2. creating a read_erc20 contract that reads the LLM ERC20 contract
    3. creating a read_erc20 contract that reads the previous read_erc20 contract
    Repeats step 3 a few times.

    It's like a linked list, but with contracts.
    """
    TOKEN_TOTAL_SUPPLY = 1000
    current_directory = os.path.dirname(os.path.abspath(__file__))
    contract_file = os.path.join(current_directory, "read_erc20.py")

    # LLM ERC20
    contract_code = open("examples/contracts/llm_erc20.py", "r").read()

    # Deploy Contract
    last_contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account,
        contract_code,
        [TOKEN_TOTAL_SUPPLY],
    )
    assert has_success_status(transaction_response_deploy)

    # Read ERC20
    contract_code = open(contract_file, "r").read()

    for i in range(5):
        print(f"Deploying contract, iteration {i}")

        # deploy contract
        last_contract_address, transaction_response_deploy = (
            deploy_intelligent_contract(
                from_account,
                contract_code,
                [last_contract_address],
            )
        )
        assert has_success_status(transaction_response_deploy)

        # check balance
        contract_state = call_contract_method(
            last_contract_address,
            from_account,
            "get_balance_of",
            [from_account.address],
        )
        assert contract_state == TOKEN_TOTAL_SUPPLY
