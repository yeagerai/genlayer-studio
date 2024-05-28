# consensus/services/state_db_service.py

import json

from database.db_client import DBClient

class StateDBService:
    def __init__(self, db_client: DBClient):
        self.db_client = db_client
        self.db_state_table = "current_state"

    def get_account_by_address(self, account_address: str) -> dict:
        condition = f"id = {account_address}"
        result = self.db_client.get(self.db_state_table, condition)
        if (result[0]):
            return {
                "id": result[0]["id"],
                "balance": json.loads(result[0]["data"])["balance"],
            }
        return None

    def create_new_account(self, account_data: dict) -> None:
        account_state = {
            "id": account_data["id"],
            "data": json.dumps({"balance": account_data["balance"]}),
        }
        self.db_client.insert(self.db_state_table, account_state)

    def update_account(self, account_data: dict) -> None:
        update_condition = f"id = {account_data["id"]}"
        account_state = {
            "data": json.dumps({"balance": account_data["balance"]}),
        }
        self.db_client.update(self.db_state_table, account_state, update_condition)

    def create_new_contract_account(
        self,
        contract_address: str,
        contract_data: str,
    ) -> None:
        contract_state = {
            "id": contract_address,
            "data": contract_data,
        }
        self.db_client.insert(self.db_state_table, contract_state)
