import json
import os
import time

from tests.common.accounts import create_new_account
from tests.common.request import (
    call_contract_method,
    deploy_intelligent_contract,
    send_transaction,
    wait_for_transaction,
)
from tests.common.response import has_success_status

from backend.node.types import Address


def test_multi_tenant_storage(setup_validators):
    """
    This test verifies the functionality of a multi-tenant storage contract. It deploys two separate storage contracts
    and a multi-tenant storage contract that manages them. The test aims to:

    1. Deploy two different storage contracts with initial storage values.
    2. Deploy a multi-tenant storage contract that can interact with multiple storage contracts.
    3. Test the ability of the multi-tenant contract to update and retrieve storage values for multiple users
       across different storage contracts.
    4. Ensure the multi-tenant contract correctly assigns users to storage contracts and manages their data.

    This test demonstrates contract-to-contract interactions and multi-tenant data management.
    """
    main_account = create_new_account()
    user_account_a = create_new_account()
    user_account_b = create_new_account()

    current_directory = os.path.dirname(os.path.abspath(__file__))

    # Storage Contracts
    contract_code = open("examples/contracts/storage.py", "r").read()

    ## Deploy first Storage Contract
    first_storage_contract_address, transaction_response_deploy = (
        deploy_intelligent_contract(
            main_account,
            contract_code,
            ["initial_storage_a"],
        )
    )
    assert has_success_status(transaction_response_deploy)

    ## Deploy second Storage Contract

    second_storage_contract_address, transaction_response_deploy = (
        deploy_intelligent_contract(
            main_account,
            contract_code,
            ["initial_storage_b"],
        )
    )
    assert has_success_status(transaction_response_deploy)

    # Deploy Multi Tenant Storage Contract
    contract_file = os.path.join(current_directory, "multi_tenant_storage.py")
    contract_code = open(contract_file, "r").read()

    multi_tenant_storage_address, transaction_response_deploy = (
        deploy_intelligent_contract(
            main_account,
            contract_code,
            [
                [
                    first_storage_contract_address,
                    second_storage_contract_address,
                ]
            ],
        )
    )
    assert has_success_status(transaction_response_deploy)

    # update storage for first contract
    transaction_response_call = send_transaction(
        user_account_a,
        multi_tenant_storage_address,
        "update_storage",
        ["user_a_storage"],
    )

    assert has_success_status(transaction_response_call)

    # update storage for second contract
    transaction_response_call = send_transaction(
        user_account_b,
        multi_tenant_storage_address,
        "update_storage",
        ["user_b_storage"],
    )

    assert has_success_status(transaction_response_call)

    # wait for triggered transactions to be processed
    triggered_transactions = transaction_response_call["triggered_transactions"]

    for triggered_transaction in triggered_transactions:
        wait_for_transaction(triggered_transaction)

    # get all storages
    storages = call_contract_method(
        multi_tenant_storage_address,
        main_account,
        "get_all_storages",
        [],
    )

    assert storages == {
        second_storage_contract_address: "user_a_storage",
        first_storage_contract_address: "user_b_storage",
    }
