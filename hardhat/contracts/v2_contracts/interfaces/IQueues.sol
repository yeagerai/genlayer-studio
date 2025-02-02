// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./ITransactions.sol";

interface IQueues {
	enum QueueType {
		None,
		Pending,
		Accepted,
		Undetermined
	}

	struct LastQueueModification {
		QueueType lastQueueType;
		uint256 lastQueueTimestamp;
	}

	function getTransactionQueueType(
		bytes32 txId
	) external view returns (QueueType);

	function getTransactionQueuePosition(
		bytes32 txId
	) external view returns (uint);

	function getTransactionActivator(
		bytes32 txId
	) external view returns (address);

	function voteCommittedForTx(
		bytes32 txId,
		address validator
	) external returns (bool);

	function revealVoteForTx(
		bytes32 txId,
		ITransactions.VoteType voteType,
		address validator
	) external returns (bool, ITransactions.ResultType);

	function isVoteRevealed(
		bytes32 txId,
		address validator
	) external view returns (bool);

	function getLeader(bytes32 txId) external view returns (address);

	function isValidator(
		bytes32 txId,
		address validator
	) external view returns (bool);

	function isVoteCommitted(
		bytes32 txId,
		address validator
	) external view returns (bool);

	function isAcceptanceTimeoutExpired(
		bytes32 txId
	) external view returns (bool);

	function getLastQueueModification(
		bytes32 txId
	) external view returns (LastQueueModification memory);

	function addTransactionToPendingQueue(
		address recipient,
		bytes32 txId
	) external returns (uint256, bytes32[] memory);

	function activateTransaction(bytes32 txId) external;
	// function setRecipientRandomSeed(
	// 	address recipient,
	// 	bytes32 randomSeed
	// ) public;

	// function getRecipientRandomSeed(
	// 	address recipient
	// ) public view returns (bytes32);

	function addTransactionToFinalizedQueue(
		address recipient,
		bytes32 txId
	) external;

	function isAtFinalizedQueueHead(
		address recipient,
		bytes32 txId
	) external view returns (bool);

	function isAtPendingQueueHead(
		address recipient,
		bytes32 txId
	) external view returns (bool);

	function addTransactionToAcceptedQueue(
		address recipient,
		bytes32 txId
	) external returns (uint slot);

	function addTransactionToUndeterminedQueue(
		address recipient,
		bytes32 txId
	) external returns (uint slot);

	function removeTransactionFromPendingQueue(
		address recipient,
		bytes32 txId
	) external;
}