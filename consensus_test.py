import json
import os
from web3 import Web3
from typing import Optional, Dict, Any
from pathlib import Path
import re


class ConsensusService:
    def __init__(self):
        """
        Initialize the ConsensusService class
        """
        # Connect to Hardhat Network - probamos varias URLs
        urls_to_try = [
            "http://hardhat:8545",
            "http://localhost:8545",
            "http://127.0.0.1:8545",
            "http://0.0.0.0:8545",
            "http://genlayer-studio-hardhat-1:8545",
        ]

        connected = False
        for url in urls_to_try:
            print(f"Trying to connect to: {url}")
            self.web3 = Web3(Web3.HTTPProvider(url))
            if self.web3.is_connected():
                print(f"✅ Successfully connected to {url}")
                connected = True
                # Mostrar información sobre la conexión
                print(f"Chain ID: {self.web3.eth.chain_id}")
                print(f"Block number: {self.web3.eth.block_number}")
                print(f"Accounts: {self.web3.eth.accounts[:3]}...")
                break
            else:
                print(f"❌ Failed to connect to {url}")

        if not connected:
            raise ConnectionError(f"Failed to connect to any Ethereum node")


# Ejecutar el test
if __name__ == "__main__":
    try:
        print("Starting ConsensusService test...")
        service = ConsensusService()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
