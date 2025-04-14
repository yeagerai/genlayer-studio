# database_handler/contract_snapshot.py
from .models import CurrentState
from sqlalchemy.orm import Session
from typing import Optional


class ContractSnapshot:
    """
    Warning: if you initialize this class with a contract_address:
    - The contract_address must exist in the database.
    - `self.contract_data`, `self.contract_code` and `self.encoded_state` will be loaded from the database **only once** at initialization.
    """

    contract_address: str
    contract_code: str
    encoded_state: dict[str, str]
    balance: int
    states: dict[str, dict[str, str]]

    def __init__(self, contract_address: str | None, session: Session):
        self.session = session

        if contract_address is not None:
            self.contract_address = contract_address

            contract_account = self._load_contract_account()
            self.contract_data = contract_account.data
            self.contract_code = self.contract_data["code"]
            self.balance = contract_account.balance

            if ("accepted" in self.contract_data["state"]) and (
                isinstance(self.contract_data["state"]["accepted"], dict)
            ):
                self.states = self.contract_data["state"]
            else:
                # Convert old state format
                self.states = {"accepted": self.contract_data["state"], "finalized": {}}
            self.encoded_state = self.states["accepted"]

    def to_dict(self):
        return {
            "contract_address": (
                self.contract_address if self.contract_address else None
            ),
            "contract_code": self.contract_code if self.contract_code else None,
            "encoded_state": self.encoded_state if self.encoded_state else {},
            "states": self.states if self.states else {"accepted": {}, "finalized": {}},
        }

    @classmethod
    def from_dict(cls, input: dict | None) -> Optional["ContractSnapshot"]:
        if input:
            instance = cls.__new__(cls)
            instance.session = None
            instance.contract_address = input.get("contract_address", None)
            instance.contract_code = input.get("contract_code", None)
            instance.encoded_state = input.get("encoded_state", {})
            instance.states = input.get("states", {"accepted": {}, "finalized": {}})
            return instance
        else:
            return None

    def _load_contract_account(self) -> CurrentState:
        """Load and return the current state of the contract from the database."""
        result = (
            self.session.query(CurrentState)
            .filter(CurrentState.id == self.contract_address)
            .one_or_none()
        )

        if result is None:
            raise Exception(f"Contract {self.contract_address} not found")

        return result
