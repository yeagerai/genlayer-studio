import json
import os
from web3 import Web3
from typing import Optional, Dict, Any
from pathlib import Path
from backend.protocol_rpc.message_handler.types import EventType, EventScope, LogEvent


class ConsensusService:
    def __init__(self):
        """
        Initialize the ConsensusService class
        """
        # Connect to Hardhat Network
        port = os.environ.get("HARDHAT_PORT")
        url = os.environ.get("HARDHAT_URL")
        hardhat_url = f"{url}:{port}"
        self.web3 = Web3(Web3.HTTPProvider(hardhat_url))

        if not self.web3.is_connected():
            raise ConnectionError(f"Failed to connect to Hardhat node at {hardhat_url}")

    def load_contract(self, contract_name: str) -> Optional[dict]:
        """
        Load contract deployment data and compiled contract data

        Args:
            contract_name (str): The name of the contract to load

        Returns:
            Optional[dict]: The contract deployment data or None if loading fails
        """
        try:
            # compiled_data = self._load_compiled_contract(contract_name)
            deployment_data = self._load_deployment_data(contract_name)

            # if not compiled_data or not deployment_data:
            #     return None

            return {
                "address": deployment_data["address"],
                "abi": deployment_data["abi"],
                "bytecode": deployment_data["bytecode"],
            }

        except Exception as e:
            print(f"[CONSENSUS_SERVICE] Error loading contract: {str(e)}")
            return None

    def _load_compiled_contract(self, contract_name: str) -> Optional[Dict[str, Any]]:
        """
        Load compiled contract data from artifacts

        Args:
            contract_name (str): The name of the contract to load

        Returns:
            Optional[Dict[str, Any]]: The compiled contract data or None if loading fails
        """
        try:
            compiled_contract_path = (
                Path(
                    f"/app/hardhat/artifacts/contracts/v2_contracts/{contract_name}.sol"
                )
                / f"{contract_name}.json"
            )

            if not compiled_contract_path.exists():
                print(
                    f"[CONSENSUS_SERVICE]: Compiled contract not found at {compiled_contract_path}"
                )
                return None

            with open(compiled_contract_path, "r") as f:
                return json.load(f)

        except Exception as e:
            print(f"[CONSENSUS_SERVICE]: Error loading compiled contract: {str(e)}")
            return None

    def _load_deployment_data(self, contract_name: str) -> Optional[Dict[str, Any]]:
        """
        Load contract deployment data from deployments

        Args:
            contract_name (str): The name of the contract to load

        Returns:
            Optional[Dict[str, Any]]: The deployment data or None if loading fails
        """
        try:
            deployment_path = (
                Path("/app/hardhat/deployments/localhost") / f"{contract_name}.json"
            )

            if not deployment_path.exists():
                print(
                    f"[CONSENSUS_SERVICE]: Deployment file not found at {deployment_path}"
                )
                return None

            with open(deployment_path, "r") as f:
                return json.load(f)

        except Exception as e:
            print(f"[CONSENSUS_SERVICE]: Error loading deployment data: {str(e)}")
            return None

    def forward_transaction(self, transaction: dict) -> str:
        """
        Forward a transaction to the consensus rollup
        """
        try:
            tx_hash = self.web3.eth.send_raw_transaction(transaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            return receipt
        except Exception as e:
            print(f"[CONSENSUS_SERVICE]: Error forwarding transaction: {str(e)}")
            return None
