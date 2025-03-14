import json
import os
from web3 import Web3
from typing import Optional, Dict, Any
from pathlib import Path
from backend.protocol_rpc.message_handler.types import EventType, EventScope, LogEvent
import re


class ConsensusService:
    def __init__(self):
        """
        Initialize the ConsensusService class
        """
        # Connect to Hardhat Network - probamos varias URLs
        urls_to_try = [
            os.environ.get("HARDHAT_URL", "http://hardhat")
            + ":"
            + os.environ.get("HARDHAT_PORT", "8545"),
            "http://hardhat:8545",  # Nombre del servicio en la red Docker
            "http://genlayer-studio-hardhat-1:8545",  # Nombre completo del contenedor
            "http://localhost:8545",
            "http://127.0.0.1:8545",
            "http://0.0.0.0:8545",
            "http://jsonrpc:8545",
            "http://genlayer-studio_default:8545",
        ]

        connected = False
        for url in urls_to_try:
            print(f"[CONSENSUS_SERVICE] Trying to connect to: {url}")
            self.web3 = Web3(Web3.HTTPProvider(url))
            if self.web3.is_connected():
                print(f"[CONSENSUS_SERVICE] ✅ Successfully connected to {url}")
                connected = True
                # Mostrar información sobre la conexión
                print(f"[CONSENSUS_SERVICE] Chain ID: {self.web3.eth.chain_id}")
                print(f"[CONSENSUS_SERVICE] Block number: {self.web3.eth.block_number}")
                break
            else:
                print(f"[CONSENSUS_SERVICE] ❌ Failed to connect to {url}")

        if not connected:
            print(f"[CONSENSUS_SERVICE] Failed to connect to any Ethereum node")

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

    def forward_transaction(
        self, transaction: dict, from_address: str, retry: bool = True
    ) -> str:
        """
        Forward a transaction to the consensus rollup and wait for NewTransaction event
        """
        try:
            tx_hash = self.web3.eth.send_raw_transaction(transaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

            # Load ConsensusMain contract
            consensus_contract_data = self.load_contract("ConsensusMain")
            if not consensus_contract_data:
                print("[CONSENSUS_SERVICE]: Failed to load ConsensusMain contract")
                return None

            # Create contract instance
            consensus_contract = self.web3.eth.contract(
                address=consensus_contract_data["address"],
                abi=consensus_contract_data["abi"],
            )

            # Get NewTransaction events from receipt
            new_tx_events = consensus_contract.events.NewTransaction().process_receipt(
                receipt
            )

            if new_tx_events:
                # Extract event data
                tx_id = new_tx_events[0]["args"]["txId"]
                recipient = new_tx_events[0]["args"]["recipient"]
                activator = new_tx_events[0]["args"]["activator"]

                # Convert tx_id from bytes to hex string for better readability
                tx_id_hex = "0x" + tx_id.hex() if isinstance(tx_id, bytes) else tx_id

                return {
                    "receipt": receipt,
                    "tx_id": tx_id,
                    "tx_id_hex": tx_id_hex,  # Adding hex version for easier reading
                    "recipient": recipient,
                    "activator": activator,
                }
            else:
                print("[CONSENSUS_SERVICE]: No NewTransaction event found in receipt")
                return receipt

        except Exception as e:
            error_str = str(e)
            error_type = (
                "nonce_too_high"
                if "nonce too high" in error_str.lower()
                else "nonce_too_low" if "nonce too low" in error_str.lower() else None
            )
            if error_type:
                # Extract expected and current nonce from error message
                match = re.search(
                    r"Expected nonce to be (\d+) but got (\d+)", error_str
                )
                if match:
                    current_nonce = int(match.group(2))

                    # Set the nonce to the expected value
                    print(
                        f"[CONSENSUS_SERVICE]: Setting nonce for {from_address} to {current_nonce}"
                    )
                    self.web3.provider.make_request(
                        "hardhat_setNonce", [from_address, hex(current_nonce)]
                    )

                    if retry:
                        return self.forward_transaction(
                            transaction, from_address, retry=False
                        )
                else:
                    print(
                        f"[CONSENSUS_SERVICE]: Could not parse nonce from error message: {error_str}"
                    )

            print(f"[CONSENSUS_SERVICE]: Error forwarding transaction: {error_str}")
            return None
