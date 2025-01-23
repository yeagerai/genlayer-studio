// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./ITransactions.sol";

interface IAppeals {
	struct Appeal {
		address[] validators;
		ITransactions.TransactionStatus originalStatus;
		uint voteRevealedCount;
		ITransactions.ResultType result;
		bytes32[] voteHashes;
		ITransactions.VoteType[] validatorVotes;
		ITransactions.ResultType[] resultTypes;
	}

	function isAppealValidator(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool);

	function getValidatorsForAppeal(
		bytes32 _tx_id,
		uint _appealIndex
	) external view returns (address[] memory);

	function setAppealData(
		bytes32 _tx_id,
		ITransactions.TransactionStatus _originalStatus,
		address[] memory _validators
	) external returns (uint appealIndex_);
	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external returns (bool isLastVote);
	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		ITransactions.VoteType _voteType,
		address _validator
	)
		external
		returns (
			bool isLastVote,
			ITransactions.ResultType majorVoted,
			ITransactions.TransactionStatus originalStatus
		);
}