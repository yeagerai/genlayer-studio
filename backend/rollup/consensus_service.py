import json
import os
from web3 import Web3
from typing import Optional, Dict, Any
from pathlib import Path
from hexbytes import HexBytes


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

        # Load the ConsensusMain ABI
        contract_data = self.load_contract("ConsensusMain")
        if not contract_data:
            raise Exception("Failed to load ConsensusMain contract")
        self.consensus_contract = self.web3.eth.contract(
            address=contract_data["address"], abi=contract_data["abi"]
        )

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
            print(f"[CONSENSUS_SERVICE]: Error loading contract: {str(e)}")
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

    def forward_transaction(self, transaction: str | HexBytes) -> str:
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

    def emit_transaction_event(self, event_name: str, account: dict, *args):
        """
        Generic method to emit transaction events

        Args:
            event_name (str): Name of the event function to call
            account (dict): Account object containing address and private key
            *args: Arguments to pass to the event function
        """
        if "private_key" in account:
            account_address = account["address"]
            account_private_key = account["private_key"]
        else:
            print(
                f"[CONSENSUS_SERVICE]: Error emitting {event_name}: Account object must contain private_key"
            )
            return None

        try:
            # Get the function from the contract
            event_function = getattr(self.consensus_contract.functions, event_name)

            # Build and send transaction
            tx = event_function(*args).build_transaction(
                {
                    "from": account_address,
                    "gas": 500000,
                    "gasPrice": 0,
                    "nonce": self.web3.eth.get_transaction_count(account_address),
                }
            )

            # Sign and send transaction
            signed_tx = self.web3.eth.account.sign_transaction(
                tx, private_key=account_private_key
            )

            return self.forward_transaction(signed_tx.raw_transaction)

        except Exception as e:
            print(f"[CONSENSUS_SERVICE]: Error emitting {event_name}: {str(e)}")
            return None
