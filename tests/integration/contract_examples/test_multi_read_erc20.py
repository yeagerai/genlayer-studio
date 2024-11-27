import json
import os
from backend.node.types import Address

from tests.common.accounts import create_new_account
from tests.common.request import (
    call_contract_method,
    deploy_intelligent_contract,
    send_transaction,
)
from tests.common.response import has_success_status


def test_multi_read_erc20(setup_validators):
    """
    This test verifies the functionality of a multi-read ERC20 contract. It deploys two separate ERC20 token contracts
    (referred to as 'doge' and 'shiba') and a multi-read ERC20 contract. The test aims to:

    1. Deploy two different ERC20 token contracts with a total supply of 1000 tokens each.
    2. Deploy a multi-read ERC20 contract that can interact with multiple ERC20 tokens.
    3. Test the ability of the multi-read contract to update and retrieve token balances for multiple ERC20 tokens
       and multiple accounts simultaneously.
    4. Ensure the multi-read contract correctly maintains and reports balances for different account-token combinations.

    This test demonstrates the integration contract to contract reads
    """
    TOKEN_TOTAL_SUPPLY = 1000
    from_account_doge = create_new_account()
    from_account_shiba = create_new_account()

    current_directory = os.path.dirname(os.path.abspath(__file__))

    # LLM ERC20
    contract_code = open("examples/contracts/llm_erc20.py", "r").read()

    ## Deploy first LLM ERC20 Contract
    doge_contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account_doge,
        contract_code,
        [TOKEN_TOTAL_SUPPLY],
    )
    assert has_success_status(transaction_response_deploy)

    ## Deploy second LLM ERC20 Contract

    shiba_contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account_shiba,
        contract_code,
        [TOKEN_TOTAL_SUPPLY],
    )
    assert has_success_status(transaction_response_deploy)

    # Deploy Multi Read ERC20 Contract
    contract_file = os.path.join(current_directory, "multi_read_erc20.py")
    contract_code = open(contract_file, "r").read()

    multi_read_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account_doge,
        contract_code,
        [],
    )
    assert has_success_status(transaction_response_deploy)

    # update balances for doge account
    transaction_response_call = send_transaction(
        from_account_doge,
        multi_read_address,
        "update_token_balances",
        [from_account_doge.address, [doge_contract_address, shiba_contract_address]],
    )

    assert has_success_status(transaction_response_call)

    # check balances
    call_method_response_get_balances = call_contract_method(
        multi_read_address,
        from_account_doge,
        "get_balances",
        [],
    )

    assert call_method_response_get_balances == {
        from_account_doge.address: {
            doge_contract_address: TOKEN_TOTAL_SUPPLY,
            shiba_contract_address: 0,
        }
    }

    # update balances for shiba account
    transaction_response_call = send_transaction(
        from_account_shiba,
        multi_read_address,
        "update_token_balances",
        [from_account_shiba.address, [doge_contract_address, shiba_contract_address]],
    )

    assert has_success_status(transaction_response_call)

    # check balances
    call_method_response_get_balances = call_contract_method(
        multi_read_address,
        from_account_shiba,
        "get_balances",
        [],
    )

    assert call_method_response_get_balances == {
        from_account_doge.address: {
            doge_contract_address: TOKEN_TOTAL_SUPPLY,
            shiba_contract_address: 0,
        },
        from_account_shiba.address: {
            doge_contract_address: 0,
            shiba_contract_address: TOKEN_TOTAL_SUPPLY,
        },
    }
