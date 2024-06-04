from typing import Optional
from backend.node.genvm.base import GenVM


class Node:
    def __init__(self, address, validator_mode, config, leader_outputs: Optional[dict]):
        self.address = address
        self.validator_mode = validator_mode
        self.config = config
        self.leader_outputs = leader_outputs
        self.genvm = GenVM({}, self.validator_mode, self.config)

    def deploy_contract(self, code_to_deploy, from_address, constructor_args):
        try:
            receipt = self.genvm.deploy_contract(
                code_to_deploy, from_address, constructor_args
            )
        except Exception as e:
            ...
            # create error receipt
        return receipt

    def exec_transaction(self, from_address, encoded_state, function_name):
        try:
            receipt = self.genvm.run_contract(
                from_address, encoded_state, function_name
            )
        except Exception as e:
            ...
            # create error receipt
        return {"vote": "agree", "result": result}

    def get_contract_data(code: str, state: str, method_name: str, method_args: list):
        try:
            return GenVM.get_contract_data(code, state, method_name, method_args)
        except Exception as e:
            ...
            # create error receipt

    def get_contract_schema(code: str):
        try:
            return GenVM.get_contract_schema(code)
        except Exception as e:
            ...
            # create error receipt
