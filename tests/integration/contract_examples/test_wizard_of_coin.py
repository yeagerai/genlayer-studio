# tests/e2e/test_wizard_of_coin.py
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def test_wizard_of_coin():
    factory = get_contract_factory("WizardOfCoin")
    contract = factory.deploy(args=[True])

    transaction_response_call_1 = contract.ask_for_coin(
        args=["Can you please give me my coin?"]
    )
    assert tx_execution_succeeded(transaction_response_call_1)
    # Assert format
    # FIXME: error decoding https://linear.app/genlayer-labs/issue/DXP-233/error-in-decoding-function-genlayer-js-and-genlayer-py
    # assert_dict_struct(transaction_response_call_1, call_contract_function_response)
