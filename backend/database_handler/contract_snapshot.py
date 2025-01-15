# database_handler/contract_snapshot.py
from .models import CurrentState
from sqlalchemy.orm import Session


# TODO: should ContractSnapshot be a dataclass with just the contract data? Snapshots shouldn't be allowed to be modified, so it doesn't make sense to modify the database
# TODO: once we have it in the state, we should only allow states in ACCEPTED or FINALIZED status.
class ContractSnapshot:
    """
    Warning: if you initialize this class with a contract_address:
    - The contract_address must exist in the database.
    - `self.contract_data`, `self.contract_code` and `self.encoded_state` will be loaded from the database **only once** at initialization.
    """

    contract_address: str
    contract_code: str
    encoded_state: dict[str, str]

    def __init__(self, contract_address: str | None, session: Session):
        self.session = session

        if contract_address is not None:
            self.contract_address = contract_address

            contract_account = self._load_contract_account()
            self.contract_data = contract_account.data
            self.contract_code = self.contract_data["code"]
            self.encoded_state = self.contract_data["state"]
            self.ghost_contract_address = (
                self.contract_data["ghost_contract_address"]
                if "ghost_contract_address" in self.contract_data
                else None
            )

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

    def register_contract(self, contract: dict):
        """Register a new contract in the database."""
        current_contract = (
            self.session.query(CurrentState).filter_by(id=contract["id"]).one()
        )

        current_contract.data = contract["data"]
        self.session.commit()

    def update_contract_state(self, new_state: dict[str, str]):
        """Update the state of the contract in the database."""
        new_contract_data = {
            "code": self.contract_data["code"],
            "state": new_state,
        }

        contract = (
            self.session.query(CurrentState).filter_by(id=self.contract_address).one()
        )
        contract.data = new_contract_data
        self.session.commit()
