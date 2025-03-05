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

    def forward_transaction(
        self, transaction: dict, from_address: str, retry: bool = True
    ) -> str:
        """
        Forward a transaction to the consensus rollup and wait for NewTransaction event
        """
        try:
            tx_hash = self.web3.eth.send_raw_transaction(transaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            tx_details = self._get_transaction_details(tx_hash)
            print(f"[CONSENSUS_SERVICE]: Transaction forwarded: {tx_hash}")
            print(f"[CONSENSUS_SERVICE]: Transaction receipt: {receipt}")
            print(f"[CONSENSUS_SERVICE]: Transaction details: {tx_details}")

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
            print(f"[CONSENSUS_SERVICE]: New transaction events: {new_tx_events}")
            if new_tx_events:
                tx_id = new_tx_events[0]["args"]["tx_id"]
                recipient = new_tx_events[0]["args"]["recipient"]
                activator = new_tx_events[0]["args"]["activator"]
                print(
                    f"[CONSENSUS_SERVICE]: New transaction created - ID: {tx_id}, Recipient: {recipient}, Activator: {activator}"
                )
                return {
                    "receipt": receipt,
                    "tx_id": tx_id,
                    "recipient": recipient,
                    "activator": activator,
                }
            else:
                print("[CONSENSUS_SERVICE]: No NewTransaction event found in receipt")
                return receipt

        except Exception as e:
            error_str = str(e)
            if "nonce too high" in error_str.lower():
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

    def _get_transaction_details(self, tx_hash: str) -> dict:
        """
        Get detailed information about a transaction

        Args:
            tx_hash (str): The transaction hash

        Returns:
            dict: Transaction details including status and block information
        """
        try:
            # Convert string hash to bytes if needed
            if isinstance(tx_hash, str):
                tx_hash = self.web3.to_bytes(hexstr=tx_hash)

            tx = self.web3.eth.get_transaction(tx_hash)
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)

            if receipt:
                block = self.web3.eth.get_block(receipt["blockNumber"])
                return {
                    "transaction": tx,
                    "receipt": receipt,
                    "status": "Success" if receipt["status"] == 1 else "Failed",
                    "block_number": receipt["blockNumber"],
                    "block_timestamp": block["timestamp"],
                    "confirmations": self.web3.eth.block_number
                    - receipt["blockNumber"],
                }
            else:
                return {"transaction": tx, "status": "Pending", "receipt": None}

        except Exception as e:
            print(f"[CONSENSUS_SERVICE]: Error getting transaction details: {str(e)}")
            return None
