from typing import Iterator
from eth_account import Account
import pytest
import re

from tests.common.accounts import create_new_account
from tests.common.request import payload, post_request_localhost
from tests.common.response import has_success_status


def delete_validators():
    delete_validators_result = post_request_localhost(
        payload("sim_deleteAllValidators")
    ).json()
    assert has_success_status(delete_validators_result)


@pytest.fixture
def setup_validators():
    result = post_request_localhost(
        payload("sim_createRandomValidators", 5, 8, 12, ["openai"], ["gpt-4o"])
    ).json()
    assert has_success_status(result)

    yield

    delete_validators()


def setup_mock_validators(responses, eq_result=True):
    mock_provider = {
        "provider": "mock",
        "model": "mock-model",
        "config": {},
        "plugin": "mock",
        "plugin_config": {},
    }
    response = post_request_localhost(payload("sim_addProvider", mock_provider)).json()
    assert has_success_status(response)

    # Create 5 mock validators with the same responses
    for i in range(5):
        result = post_request_localhost(
            payload(
                "sim_createValidator",
                8,
                "mock",
                f"mock-model-{i}",
                {"responses": responses, "eq_result": eq_result},
                "mock",
                {},
            )
        ).json()
        assert has_success_status(result)


def cleanup_mock_validators():
    # Clean up all validators
    delete_validators()

    # Clean up mock provider
    providers_response = post_request_localhost(
        payload("sim_getProvidersAndModels")
    ).json()
    assert has_success_status(providers_response)

    for provider in providers_response["result"]:
        if provider["provider"] == "mock":
            response = post_request_localhost(
                payload("sim_deleteProvider", provider["id"])
            ).json()
            assert has_success_status(response)


def get_prompts_from_contract_code(contract_code: str) -> list[str]:
    prompts = re.findall(r'=\s*f?"""(.*?)"""', contract_code, re.DOTALL)
    return prompts


@pytest.fixture
def from_account() -> Iterator[Account]:
    account = create_new_account()
    yield account
