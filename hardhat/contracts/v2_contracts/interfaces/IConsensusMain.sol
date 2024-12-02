// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IConsensusMain {
	struct addTransactionParams {
		address sender;
		bytes data;
	}

	function addTransaction(bytes memory _transaction) external;

	function activateTransaction(bytes32 _tx_id) external;

	function proposeReceipt(bytes memory _receipt) external;

	function commitVote(bytes32 _tx_id, bytes32 _voteHash) external;

	function revealVote(bytes32 _tx_id, bytes32 _voteHash) external;

	function finalizeTransaction(bytes32 _tx_id) external;
}
