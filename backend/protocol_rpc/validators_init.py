import json
from dataclasses import dataclass
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.validators_registry import ValidatorsRegistry


@dataclass
class ValidatorConfig:
    stake: int
    provider: str
    model: str
    config: dict | None = None
    plugin: str | None = None
    plugin_config: dict | None = None
    amount: int = 1


def initialize_validators(
    validators_json: str,
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    validator_creator=None,
):
    """
    Idempotently initialize validators from a JSON string by deleting all existing validators and creating new ones.

    Args:
        validators_json: JSON string containing validator configurations
        validators_registry: Registry to store validator information
        accounts_manager: AccountsManager to create validator accounts
        validator_creator: Function to create validators (defaults to endpoints.create_validator)
    """

    if not validators_json:
        print("No validators to initialize")
        return

    # If no validator_creator is provided, import the default one
    if validator_creator is None:
        from backend.protocol_rpc.endpoints import create_validator

        validator_creator = create_validator

    try:
        validators_data = json.loads(validators_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in validators_json: {str(e)}")

    if not isinstance(validators_data, list):
        raise ValueError("validators_json must contain a JSON array")

    # Delete all existing validators
    validators_registry.delete_all_validators()

    # Create new validators
    for validator_data in validators_data:
        try:
            validator = ValidatorConfig(**validator_data)

            for _ in range(validator.amount):
                validator_creator(
                    validators_registry,
                    accounts_manager,
                    validator.stake,
                    validator.provider,
                    validator.model,
                    validator.config,
                    validator.plugin,
                    validator.plugin_config,
                )

        except Exception as e:
            raise ValueError(f"Failed to create validator `{validator_data}`: {str(e)}")

    # Register the leader as a validator
    leader_validator = ValidatorConfig(
        stake=100,  # Example stake value
        provider="leader_provider",
        model="leader_model", 
        config=None,
        plugin=None,
        plugin_config=None,
        amount=1
    )
    try:
        validator_creator(
            validators_registry,
            accounts_manager,
            leader_validator.stake,
            leader_validator.provider,
            leader_validator.model,
            leader_validator.config,
            leader_validator.plugin,
            leader_validator.plugin_config,
        )
    except Exception as e:
        raise ValueError(f"Failed to register leader as validator: {str(e)}")
