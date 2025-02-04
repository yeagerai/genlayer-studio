// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./utils/Errors.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IAppeals.sol";

contract Appeals is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	event GenConsensusSet(address genConsensus);

	address public genConsensus;

	mapping(bytes32 => mapping(uint => address[])) public validatorsForAppeal;
	mapping(bytes32 => mapping(address => uint)) public validatorIndexInAppeal;
	mapping(bytes32 => uint) public currentAppealIndex;
	mapping(bytes32 => mapping(uint => IAppeals.Appeal)) private appeals;
	mapping(bytes32 => mapping(uint => uint)) public commitedVotes;
	mapping(bytes32 => mapping(uint => mapping(uint => bool)))
		public voteRevealed;

	receive() external payable {}

	function initialize() public initializer {
		__Ownable_init(msg.sender);
		__Ownable2Step_init();
		__ReentrancyGuard_init();
		__AccessControl_init();
	}

	function setAppealData(
		bytes32 _tx_id,
		ITransactions.TransactionStatus _originalStatus,
		address[] memory _validators
	) external returns (uint appealIndex_) {
		// Implementation of setAppealData
		appealIndex_ = ++currentAppealIndex[_tx_id];
		appeals[_tx_id][appealIndex_].originalStatus = _originalStatus;
		appeals[_tx_id][appealIndex_].validators = _validators;
		appeals[_tx_id][appealIndex_].voteHashes = new bytes32[](
			_validators.length
		);
		for (uint i = 1; i <= _validators.length; i++) {
			validatorIndexInAppeal[_tx_id][_validators[i - 1]] = i;
		}
	}

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external onlyGenConsensus returns (bool isLastVote) {
		uint appealIndex = currentAppealIndex[_tx_id];
		uint validatorIndex = validatorIndexInAppeal[_tx_id][_validator];
		if (validatorIndex == 0) {
			revert Errors.ValidatorNotInAppeal();
		}
		if (
			appeals[_tx_id][appealIndex].voteHashes[validatorIndex - 1] !=
			bytes32(0)
		) {
			revert Errors.VoteAlreadyCommittedForAppeal();
		}
		appeals[_tx_id][appealIndex].voteHashes[
			validatorIndex - 1
		] = _commitHash;
		commitedVotes[_tx_id][appealIndex]++;
		isLastVote =
			commitedVotes[_tx_id][appealIndex] ==
			appeals[_tx_id][appealIndex].validators.length;
	}

	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		ITransactions.VoteType _voteType,
		address _validator
	)
		external
		onlyGenConsensus
		returns (
			bool isLastVote,
			ITransactions.ResultType majorVoted,
			ITransactions.TransactionStatus originalStatus
		)
	{
		uint appealIndex = currentAppealIndex[_tx_id];
		uint validatorIndex = validatorIndexInAppeal[_tx_id][_validator] - 1;
		bool validatorRevealedAlready = voteRevealed[_tx_id][appealIndex][
			validatorIndex
		];
		if (validatorRevealedAlready) {
			revert Errors.VoteAlreadyRevealed();
		}
		if (
			appeals[_tx_id][appealIndex].validators[validatorIndex] ==
			_validator &&
			appeals[_tx_id][appealIndex].voteHashes[validatorIndex] == _voteHash
		) {
			appeals[_tx_id][appealIndex].validatorVotes.push(_voteType);
			voteRevealed[_tx_id][appealIndex][validatorIndex] = true;
			isLastVote =
				++appeals[_tx_id][appealIndex].voteRevealedCount ==
				appeals[_tx_id][appealIndex].validators.length;
		}
		majorVoted = ITransactions.ResultType(0);
		if (isLastVote) {
			majorVoted = _getMajorityVote(_tx_id, appealIndex);
			appeals[_tx_id][appealIndex].resultTypes.push(majorVoted);
			originalStatus = appeals[_tx_id][appealIndex].originalStatus;
			appeals[_tx_id][appealIndex].result = majorVoted;
			// appeals[_tx_id][appealIndex].lastVoteTimestamp = block.timestamp;
		}
	}

	function _getMajorityVote(
		bytes32 _tx_id,
		uint appealIndex
	) private view returns (ITransactions.ResultType result) {
		result = ITransactions.ResultType.Idle;
		uint validatorCount = appeals[_tx_id][appealIndex].validators.length;
		uint[] memory voteCounts = new uint[](
			uint(type(ITransactions.VoteType).max) + 1
		);
		for (
			uint i = 0;
			i < appeals[_tx_id][appealIndex].validatorVotes.length;
			i++
		) {
			voteCounts[uint(appeals[_tx_id][appealIndex].validatorVotes[i])]++;
		}

		uint maxVotes = 0;
		ITransactions.VoteType majorityVote = ITransactions.VoteType(0);
		for (uint i = 0; i < voteCounts.length; i++) {
			if (voteCounts[i] > maxVotes) {
				maxVotes = voteCounts[i];
				majorityVote = ITransactions.VoteType(i);
			}
		}
		if (maxVotes == validatorCount) {
			if (majorityVote == ITransactions.VoteType.Agree) {
				result = ITransactions.ResultType.MajorityAgree;
			} else {
				result = ITransactions.ResultType.MajorityDisagree;
			}
		} else if (maxVotes > validatorCount / 2) {
			if (majorityVote == ITransactions.VoteType.Agree) {
				result = ITransactions.ResultType.Agree;
			} else if (majorityVote == ITransactions.VoteType.Disagree) {
				result = ITransactions.ResultType.Disagree;
			} else if (majorityVote == ITransactions.VoteType.Timeout) {
				result = ITransactions.ResultType.Timeout;
			} else if (
				majorityVote == ITransactions.VoteType.DeterministicViolation
			) {
				result = ITransactions.ResultType.DeterministicViolation;
			}
		} else {
			result = ITransactions.ResultType.NoMajority;
		}
	}

	function setGenConsensus(address _genConsensus) external onlyOwner {
		genConsensus = _genConsensus;
		emit GenConsensusSet(_genConsensus);
	}

	modifier onlyGenConsensus() {
		if (msg.sender != genConsensus) {
			revert Errors.NotGenConsensus();
		}
		_;
	}

	function getAppeal(
		bytes32 _tx_id,
		uint _appealIndex
	)
		external
		view
		returns (
			address[] memory validators,
			bytes32[] memory votes,
			ITransactions.VoteType[] memory voteTypes,
			ITransactions.ResultType[] memory resultTypes
		)
	{
		IAppeals.Appeal storage appeal = appeals[_tx_id][_appealIndex];
		return (
			appeal.validators,
			appeal.voteHashes,
			appeal.validatorVotes,
			appeal.resultTypes
		);
	}

	function getValidatorsForAppeal(
		bytes32 _tx_id,
		uint _appealIndex
	) external view returns (address[] memory) {
		return appeals[_tx_id][_appealIndex].validators;
	}

	function getAppealResult(
		bytes32 _tx_id,
		uint _appealIndex
	) external view returns (ITransactions.ResultType) {
		return appeals[_tx_id][_appealIndex].result;
	}

	function isAppealValidator(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool) {
		return validatorIndexInAppeal[_tx_id][_validator] != 0;
	}
}