from typing import Iterator
from eth_account import Account
import pytest
import re
import os
from dotenv import load_dotenv

from tests.common.accounts import create_new_account
from tests.common.request import payload, post_request_localhost
from tests.common.response import has_success_status


def setup_openai_validators():
    result = post_request_localhost(
        payload("sim_createRandomValidators", 5, 8, 12, ["openai"], ["gpt-4o"])
    ).json()
    assert has_success_status(result)


def setup_mock_validators(responses: dict, eq_result: bool):
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


def delete_validators():
    delete_validators_result = post_request_localhost(
        payload("sim_deleteAllValidators")
    ).json()
    assert has_success_status(delete_validators_result)


def cleanup_mock_validators():
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


def parse_bool_env_var(env_var: str, default: str) -> bool:
    env_var = os.getenv(env_var, default)
    if env_var == "true":
        return True
    elif env_var == "false":
        return False
    else:
        raise ValueError(f"{env_var} must be true or false")


@pytest.fixture
def setup_validators():
    def _setup(responses=None, eq_result=True):
        if parse_bool_env_var("TEST_WITH_MOCK_LLMS", "true"):
            setup_mock_validators(responses if responses else {}, eq_result)
        else:
            setup_openai_validators()

    yield _setup

    delete_validators()
    if parse_bool_env_var("TEST_WITH_MOCK_LLMS", "true"):
        cleanup_mock_validators()


def get_prompts_from_contract_code(contract_code: str) -> list[str]:
    prompts = re.findall(r'=\s*f?"""(.*?)"""', contract_code, re.DOTALL)
    return prompts


@pytest.fixture
def from_account() -> Iterator[Account]:
    account = create_new_account()
    yield account


def pytest_configure(config):
    load_dotenv(override=True)
