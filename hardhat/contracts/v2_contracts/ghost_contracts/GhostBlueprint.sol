// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "../interfaces/IConsensusMain.sol";

contract GhostBlueprint is Initializable, OwnableUpgradeable {
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

	// EXTERNAL FUNCTIONS

	function addTransaction(
		uint256 _numOfInitialValidators,
		bytes memory _txData
	) external payable {
		bytes memory consensusCallData = abi.encodeWithSignature(
			"addTransaction(address,address,uint256,bytes)",
			msg.sender,
			address(this),
			_numOfInitialValidators,
			_txData
		);
		(bool success, ) = owner().call{ value: msg.value }(consensusCallData);
		require(success, "Call failed");
	}

	function handleOp(
		address to,
		bytes32 msgId,
		uint expectedNonce,
		bytes calldata data
	) external payable onlyOwner {
		require(nonce == expectedNonce, "Invalid nonce");
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