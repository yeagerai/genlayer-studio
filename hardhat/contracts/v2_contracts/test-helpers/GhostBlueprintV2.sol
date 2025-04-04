// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "../interfaces/IConsensusMain.sol";

contract GhostBlueprintV2 is Initializable, OwnableUpgradeable {
	uint private nonce;

	receive() external payable {}

	function initialize(address _owner) public initializer {
		__Ownable_init(_owner);
		nonce = 1;
	}

	// VIEW FUNCTIONS
	function getNonce() external view returns (uint) {
		return nonce;
	}

	function getNonceMultipliedByTen() external view returns (uint) {
		return nonce * 10;
	}

	// EXTERNAL FUNCTIONS

	function addTransaction() external payable {
		bool success;
		(success, ) = owner().call{ value: msg.value }(msg.data);
		require(success, "Call failed");
	}

	function handleOp(
		address to,
		bytes32 msgId,
		bytes calldata data
	) external payable onlyOwner {
		require(nonce == abi.decode(data[:32], (uint256)), "Invalid nonce");
		if (msg.value > 0) {
			(bool success, ) = to.call{ value: msg.value }(data);
			require(success, "Transaction failed");
		} else {
			(bool success, ) = to.call(data);
			require(success, "Transaction failed");
		}

		emit TransactionExecuted(to, msgId, data);
		// Increment nonce to prevent replay attacks
		nonce += 1;
	}

	// EVENTS
	event TransactionExecuted(address indexed to, bytes32 msgId, bytes data);
}