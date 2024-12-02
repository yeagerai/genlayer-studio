// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITransactions {
	struct Transaction {
		address sender;
		address recipient;
		uint256 numOfInitialValidators;
		uint256 txSlot;
		uint256 timestamp;
		uint256 lastVoteTimestamp;
		bytes32 randomSeed;
		ResultType result;
		bytes txData;
		bytes txReceipt;
		bytes[] messages;
		address[] validators;
		bytes32[] validatorVotesHash;
		VoteType[] validatorVotes;
	}

	enum TransactionStatus {
		Pending,
		Canceled,
		Proposing,
		Committing,
		Revealing,
		Accepted,
		Finalized,
		Undetermined,
		Appealed
	}
	enum VoteType {
		NotVoted,
		Agree,
		Disagree,
		Timeout,
		DeterministicViolation
	}

	enum ResultType {
		Idle,
		Agree,
		Disagree,
		Timeout,
		DeterministicViolation,
		NoMajority,
		MajorityAgree,
		MajorityDisagree
	}

	function addNewTransaction(
		bytes32 txId,
		Transaction memory newTx
	) external returns (bytes32);
	function getTransactionSeed(bytes32 txId) external view returns (bytes32);

	function getTransaction(
		bytes32 txId
	) external view returns (Transaction memory);

	function isVoteCommitted(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool);

	function proposeTransactionReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		bytes[] calldata _messages
	) external;

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external;

	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		VoteType _voteType,
		address _validator
	) external returns (bool isLastVote, ResultType result);

	function emitMessagesOnFinalization(bytes32 _tx_id) external;

	function getTransactionLastVoteTimestamp(
		bytes32 _tx_id
	) external view returns (uint256);
}
