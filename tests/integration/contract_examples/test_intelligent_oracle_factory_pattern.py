import time
from pathlib import Path
from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    call_contract_method,
)
from tests.common.response import (
    has_success_status,
    has_successful_execution,
)


cur_dir = Path(__file__).parent


def wait_for_contract_deployment(
    contract_address, from_account, max_retries=10, delay=1
):
    """
    Wait for contract to be fully deployed by attempting to call a method.
    This is used to check if the triggered deployment did deploy the contract.
    """
    for _ in range(max_retries):
        try:
            call_contract_method(contract_address, from_account, "get_dict", [])
            return True  # If successful, contract is deployed
        except Exception:
            time.sleep(delay)
    return False


def test_intelligent_oracle_factory_pattern(setup_validators, from_account):
    # Read the contract files first
    with open(cur_dir.joinpath("intelligent_oracle.py"), "rt") as f:
        intelligent_oracle_code = f.read()

    with open(cur_dir.joinpath("intelligent_oracle_factory.py"), "rt") as f:
        registry_code = f.read()

    # Deploy the Registry contract with the IntelligentOracle code
    registry_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account, registry_code, [intelligent_oracle_code]
    )

    assert has_success_status(transaction_response_deploy)
    assert has_successful_execution(transaction_response_deploy)

    markets_data = [
        {
            "prediction_market_id": "market1",
            "title": "Football Match 1",
            "description": "Predict the outcome of match 1",
            "potential_outcomes": ["Arsenal", "Crystal Palace", "Draw"],
            "rules": ["The outcome is the result of the match"],
            "data_source_domains": ["bbc.com"],
            "resolution_urls": [],
            "earliest_resolution_date": "2025-04-23T00:00:00+00:00",
            "outcome": "Draw",
        },
        {
            "prediction_market_id": "market2",
            "title": "Football Match 2",
            "description": "Predict the outcome of match 2",
            "potential_outcomes": ["Getafe", "Real Madrid", "Draw"],
            "rules": ["The outcome is the result of the match"],
            "data_source_domains": ["bbc.com"],
            "resolution_urls": [],
            "earliest_resolution_date": "2025-04-23T00:00:00+00:00",
            "outcome": "Real Madrid",
        },
    ]
    created_market_addresses = []

    # Create markets through factory
    for market_data in markets_data:
        create_result = write_intelligent_contract(
            from_account,
            registry_address,
            "create_new_prediction_market",
            [
                market_data["prediction_market_id"],
                market_data["title"],
                market_data["description"],
                market_data["potential_outcomes"],
                market_data["rules"],
                market_data["data_source_domains"],
                market_data["resolution_urls"],
                market_data["earliest_resolution_date"],
            ],
        )
        assert has_success_status(create_result)
        assert has_successful_execution(create_result)

        # Get the latest contract address from factory
        registered_addresses = call_contract_method(
            registry_address, from_account, "get_contract_addresses", []
        )
        new_market_address = registered_addresses[-1]
        created_market_addresses.append(new_market_address)

        # Wait for the new market contract to be deployed
        assert wait_for_contract_deployment(
            new_market_address, from_account
        ), f"Market contract deployment timeout for {market_data['prediction_market_id']}"

    # Verify all markets were registered
    assert len(registered_addresses) == len(markets_data)

    # Verify each market's state
    for i, market_address in enumerate(created_market_addresses):
        market_state = call_contract_method(
            market_address, from_account, "get_dict", []
        )
        expected_data = markets_data[i]

        # Verify key market properties
        assert market_state["title"] == expected_data["title"]
        assert market_state["description"] == expected_data["description"]
        assert market_state["potential_outcomes"] == expected_data["potential_outcomes"]
        assert market_state["rules"] == expected_data["rules"]
        assert (
            market_state["data_source_domains"] == expected_data["data_source_domains"]
        )
        assert market_state["resolution_urls"] == expected_data["resolution_urls"]
        assert market_state["status"] == "Active"
        assert (
            market_state["earliest_resolution_date"]
            == expected_data["earliest_resolution_date"]
        )
        assert (
            market_state["prediction_market_id"]
            == expected_data["prediction_market_id"]
        )

    # Test market resolution through factory
    evidence_url = "https://www.bbc.com/sport/football/scores-fixtures/2025-04-23"

    # Resolve first market
    for i, market_address in enumerate(created_market_addresses):
        resolve_result = write_intelligent_contract(
            from_account,
            market_address,
            "resolve",
            [evidence_url],
        )
        assert has_success_status(resolve_result)
        assert has_successful_execution(resolve_result)

        # Verify market was resolved and has the correct outcome
        market_state = call_contract_method(
            market_address, from_account, "get_dict", []
        )
        assert market_state["status"] == "Resolved"
        assert market_state["outcome"] == markets_data[i]["outcome"]
