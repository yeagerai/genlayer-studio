// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./IMessages.sol";

interface ITransactions {
	struct Transaction {
		address sender;
		address recipient;
		uint256 numOfInitialValidators;
		uint256 txSlot;
		address activator;
		TransactionStatus status;
		TransactionStatus previousStatus;
		uint256 timestamp;
		uint256 activationTimestamp;
		uint256 lastModification;
		uint256 lastVoteTimestamp;
		bytes32 randomSeed;
		bool onAcceptanceMessages;
		ResultType result;
		bytes txData;
		bytes txReceipt;
		IMessages.SubmittedMessage[] messages;
		address[] consumedValidators;
		RoundData[] roundData;
	}

	struct RoundData {
		uint256 round;
		uint256 leaderIndex;
		uint256 votesCommitted;
		uint256 votesRevealed;
		uint256 appealBond;
		uint256 rotationsLeft;
		ResultType result;
		address[] roundValidators;
		bytes32[] validatorVotesHash;
		VoteType[] validatorVotes;
	}

	struct NewRoundData {
		uint256 round;
		uint256 leaderIndex;
		address[] roundValidators;
	}

	struct ActivationInfo {
		address sender;
		address recepientAddress;
		uint256 numOfInitialValidators;
		bool initialActivation;
		uint256 rotationsLeft;
	}

	enum TransactionStatus {
		Uninitialized, // 0
		Pending, // 1
		Proposing, // 2
		Committing, // 3
		Revealing, // 4
		Accepted, // 5
		Undetermined, // 6
		Finalized, // 7
		Canceled, // 8
		AppealRevealing, // 9
		AppealCommitting // 10
	}
	enum VoteType {
		NotVoted,
		Agree,
		Disagree,
		Timeout,
		DeterministicViolation
	}

	enum ResultType {
		Idle, // 0
		Agree, // 1
		Disagree, // 2
		Timeout, // 3
		DeterministicViolation, // 4
		NoMajority, // 5
		MajorityAgree, // 6
		MajorityDisagree // 7
	}

	function addNewTransaction(
		bytes32 txId,
		Transaction memory newTx
	) external returns (bytes32);
	function getTransactionStatus(
		bytes32 txId
	) external view returns (TransactionStatus status);

	function getTransaction(
		bytes32 txId
	) external view returns (Transaction memory);

	function hasOnAcceptanceMessages(
		bytes32 _tx_id
	) external view returns (bool itHasMessagesOnAcceptance);

	function hasMessagesOnFinalization(
		bytes32 _tx_id
	) external view returns (bool itHasMessagesOnFinalization);

	function isVoteCommitted(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool);

	function getValidatorsForTransactionLastRound(
		bytes32 _tx_id
	) external view returns (address[] memory txValidators);

	function getValidatorsForLastAppeal(
		bytes32 _tx_id
	) external view returns (address[] memory appealValidators);

	function getLastAppealResult(
		bytes32 _tx_id
	) external view returns (ResultType result);

	function getTransactionRecipient(
		bytes32 txId
	) external view returns (address recipient);

	function activateTransaction(
		bytes32 txId,
		address activator,
		bytes32 randomSeed
	)
		external
		returns (
			address recepient,
			uint256 leaderIndex,
			address[] memory validators
		);

	function proposeTransactionReceipt(
		bytes32 _tx_id,
		address _leader,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages
	)
		external
		returns (
			address recipient,
			bool leaderTimeout,
			address newLeader,
			uint round
		);

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external returns (bool isLastVote);

	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		VoteType _voteType,
		address _validator
	)
		external
		returns (
			bool isLastVote,
			ResultType result,
			address recipient,
			uint round,
			bool hasMessagesOnAcceptance,
			uint rotationsLeft,
			NewRoundData memory newRoundData
		);

	function finalizeTransaction(
		bytes32 _tx_id
	) external returns (address recipient, uint256 lastVoteTimestamp);

	function cancelTransaction(
		bytes32 _tx_id,
		address _sender
	) external returns (address recipient);

	function submitAppeal(
		bytes32 _tx_id,
		uint256 _appealBond
	) external returns (address[] memory appealValidators, uint round);

	function rotateLeader(bytes32 txId) external returns (address);

	function getMessagesForTransaction(
		bytes32 _tx_id
	) external view returns (IMessages.SubmittedMessage[] memory);

	function getTransactionLastModification(
		bytes32 txId
	) external view returns (uint256);
}