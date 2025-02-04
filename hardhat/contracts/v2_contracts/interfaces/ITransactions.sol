// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./IMessages.sol";

interface ITransactions {
	struct Transaction {
		address sender;
		address recipient;
		uint256 numOfInitialValidators;
		uint256 txSlot;
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
		address[] validators;
		bytes32[] validatorVotesHash;
		VoteType[] validatorVotes;
		address[] consumedValidators;
		uint256 rotationsLeft;
	}

	struct ActivationInfo {
		address sender;
		address recepientAddress;
		uint256 numOfInitialValidators;
		bool initialActivation;
		uint256 rotationsLeft;
	}

	enum TransactionStatus {
		Pending,
		Proposing,
		Committing,
		Revealing,
		Accepted,
		Undetermined,
		Finalized,
		Canceled,
		AppealRevealing,
		AppealCommitting
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
	function getTransactionSeed(bytes32 txId) external view returns (bytes32);

	function getTransaction(
		bytes32 txId
	) external view returns (Transaction memory);

	function getTransactionActivationInfo(
		bytes32 txId
	) external view returns (ActivationInfo memory);

	function getTransactionResult(
		bytes32 txId
	) external view returns (ResultType result);

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

	function getAppealInfo(
		bytes32 _tx_id
	) external view returns (uint256 minAppealBond, bytes32 randomSeed);

	function getTransactionRecipient(
		bytes32 txId
	) external view returns (address recipient);

	function proposeTransactionReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages
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

	function setAppealData(
		bytes32 _tx_id,
		address[] memory _validators
	) external returns (uint256 appealIndex);

	function emitMessagesOnFinalization(bytes32 _tx_id) external;
	function getMessagesForTransaction(
		bytes32 _tx_id
	) external view returns (IMessages.SubmittedMessage[] memory);

	function getTransactionLastVoteTimestamp(
		bytes32 _tx_id
	) external view returns (uint256);

	function setActivationData(bytes32 txId, bytes32 randomSeed) external;
	function setRandomSeed(bytes32 txId, bytes32 randomSeed) external;

	function setActivationTimestamp(bytes32 txId, uint256 timestamp) external;

	function decreaseRotationsLeft(bytes32 txId) external;

	function addConsumedValidator(bytes32 txId, address validator) external;

	function setValidators(bytes32 txId, address[] memory validators) external;

	function getValidators(
		bytes32 txId
	) external view returns (address[] memory);

	function getValidator(
		bytes32 txId,
		uint256 index
	) external view returns (address);

	function getValidatorsLen(bytes32 txId) external view returns (uint256);

	function getConsumedValidators(
		bytes32 txId
	) external view returns (address[] memory);

	function getConsumedValidatorsLen(
		bytes32 txId
	) external view returns (uint256);

	function addValidator(bytes32 txId, address validator) external;

	function resetVotes(bytes32 txId) external;

	function rotateLeader(bytes32 txId, address leader) external;

	function addConsumedValidators(
		bytes32 txId,
		address[] memory validators
	) external;
}