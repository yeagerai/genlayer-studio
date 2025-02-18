from typing import Iterator
from eth_account import Account
import pytest

from tests.common.accounts import create_new_account
from tests.common.request import payload, post_request_localhost
from tests.common.response import has_success_status


@pytest.fixture
def setup_validators():
    result = post_request_localhost(
        payload("sim_createRandomValidators", 5, 8, 12, ["openai"], ["gpt-4o"])
    ).json()
    assert has_success_status(result)

    yield

    delete_validators_result = post_request_localhost(
        payload("sim_deleteAllValidators")
    ).json()
    assert has_success_status(delete_validators_result)


def setup_mock_validators(responses, comparison_result):
    # First delete any existing mock providers
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

    # Create 5 different mock providers with unique model names
    mock_provider = {
        "provider": "mock",
        "model": "mock-model",  # Unique model name per validator
        "config": {},
        "plugin": "mock",
        "plugin_config": {},
    }
    response = post_request_localhost(payload("sim_addProvider", mock_provider)).json()
    assert has_success_status(response)

    for i in range(5):
        result = post_request_localhost(
            payload(
                "sim_createValidator",
                8,
                "mock",
                f"mock-model-{i}",
                {"responses": responses, "comparison_result": comparison_result},
                "mock",
                {},
            )
        ).json()
        assert has_success_status(result)


def cleanup_mock_validators():
    # Cleanup
    delete_validators_result = post_request_localhost(
        payload("sim_deleteAllValidators")
    ).json()
    assert has_success_status(delete_validators_result)

    # Clean up mock providers
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


@pytest.fixture
def from_account() -> Iterator[Account]:
    account = create_new_account()
    yield account
