# database_handler/contract_processor.py
from .models import CurrentState
from .contract_snapshot import ContractSnapshot
from sqlalchemy.orm import Session


class ContractProcessor:
    """
    This class is used for updating the contract's data in the database.
    """

    def __init__(self, session: Session):
        self.session = session

    def register_contract(self, contract: dict):
        """
        Register a new contract in the database.
        """
        current_contract = (
            self.session.query(CurrentState).filter_by(id=contract["id"]).one()
        )
        current_contract.data = contract["data"]
        self.session.commit()

    def update_contract_state(
        self,
        contract_address: str,
        accepted_state: dict[str, str] | None = None,
        finalized_state: dict[str, str] | None = None,
    ):
        """
        Update the accepted and/or finalized state of the contract in the database.
        """
        contract = self.session.query(CurrentState).filter_by(id=contract_address).one()

        new_state = {
            "accepted": (
                accepted_state
                if accepted_state is not None
                else contract.data["state"]["accepted"]
            ),
            "finalized": (
                finalized_state
                if finalized_state is not None
                else contract.data["state"]["finalized"]
            ),
        }
        new_contract_data = {
            "code": contract.data["code"],
            "state": new_state,
        }

        contract.data = new_contract_data
        self.session.commit()
