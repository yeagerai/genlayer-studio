# consensus/domain/state.py

from sqlalchemy.orm import Session

from backend.domain.types import LLMProvider, Validator

from .models import Validators
from backend.errors.errors import ValidatorNotFound


# the to_dict function lives in this module and not in models.py because it's on this layer of abstraction where we convert database objects to our custom data structures
def to_dict(validator: Validators) -> dict:
    return {
        "id": validator.id,
        "address": validator.address,
        "stake": validator.stake,
        "provider": validator.provider,
        "model": validator.model,
        "config": validator.config,
        "created_at": validator.created_at.isoformat(),
    }


class ValidatorsRegistry:
    def __init__(self, session: Session):
        self.session = session
        self.db_validators_table = "validators"

    def _get_validator_or_fail(self, validator_address: str) -> Validators:
        """Private method to check if an account exists, and raise an error if not."""

        validator_data = (
            self.session.query(Validators)
            .filter(Validators.address == validator_address)
            .one_or_none()
        )

        if validator_data is None:
            raise ValidatorNotFound(validator_address)
        return validator_data

    def count_validators(self) -> int:
        return self.session.query(Validators).count()

    def get_all_validators(self) -> list:
        validators_data = self.session.query(Validators).all()
        return [to_dict(validator) for validator in validators_data]

    def get_validator(self, validator_address: str) -> dict:
        return to_dict(self._get_validator_or_fail(validator_address))

    def create_validator(self, validator: Validator) -> dict:
        self.session.add(_to_db_model(validator))
        self.session.commit()

        return self.get_validator(validator.address)

    def update_validator(
        self,
        new_validator: Validator,
    ) -> dict:
        validator = self._get_validator_or_fail(new_validator.address)

        validator.stake = new_validator.stake
        validator.provider = new_validator.provider
        validator.model = new_validator.model
        validator.config = new_validator.config

        self.session.commit()

        return to_dict(validator)

    def delete_validator(self, validator_address):
        self._get_validator_or_fail(validator_address)

        self.session.query(Validators).filter(
            Validators.address == validator_address
        ).delete()
        self.session.commit()

    def delete_all_validators(self):
        self.session.query(Validators).delete()
        self.session.commit()


def _to_domain(validator: Validators) -> Validator:
    return Validator(
        address=validator.address,
        stake=validator.stake,
        llmprovider=LLMProvider(
            provider=validator.provider,
            model=validator.model,
            config=validator.config,
            plugin=validator.plugin,
            plugin_config=validator.plugin_config,
            id=None,
        ),
        id=validator.id,
    )


def _to_db_model(validator: Validator) -> Validators:
    return Validators(
        address=validator.address,
        stake=validator.stake,
        provider=validator.llmprovider.provider,
        model=validator.llmprovider.model,
        config=validator.llmprovider.config,
        plugin=validator.llmprovider.plugin,
        plugin_config=validator.llmprovider.plugin_config,
    )
