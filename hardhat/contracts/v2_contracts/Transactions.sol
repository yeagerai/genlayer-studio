// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IMessages.sol";

contract Transactions is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
	bytes32 public constant VALIDATOR_ROLE = keccak256("VALIDATOR_ROLE");

	error CallerNotConsensus();
	error VoteAlreadyCommitted();
	mapping(bytes32 => ITransactions.Transaction) public transactions;
	mapping(bytes32 => mapping(address => uint)) public validatorIndexInTx;
	mapping(bytes32 => uint) public alreadyEmittedMessages;

	address public genConsensus;

	event GenConsensusSet(address indexed genConsensus);

	receive() external payable {}

	function initialize(address _genConsensus) public initializer {
		__Ownable2Step_init();
		__Ownable_init(msg.sender);
		__ReentrancyGuard_init();
		__AccessControl_init();
		genConsensus = _genConsensus;
	}

	function hasOnAcceptanceMessages(
		bytes32 _tx_id
	) external view returns (bool itHasMessagesOnAcceptance) {
		itHasMessagesOnAcceptance = transactions[_tx_id].onAcceptanceMessages;
	}

	function hasMessagesOnFinalization(
		bytes32 _tx_id
	) external view returns (bool itHasMessagesOnFinalization) {
		itHasMessagesOnFinalization =
			transactions[_tx_id].messages.length -
				alreadyEmittedMessages[_tx_id] >
			0;
	}

	function getMinAppealBond(
		bytes32 _tx_id
	) external view returns (uint256 minAppealBond) {
		minAppealBond = _calculateMinAppealBond(_tx_id);
	}

	function addNewTransaction(
		bytes32 txId,
		ITransactions.Transaction memory newTx
	) external onlyGenConsensus returns (bytes32) {
		transactions[txId] = newTx;
		return txId;
	}

	function proposeTransactionReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages
	) external onlyGenConsensus {
		transactions[_tx_id].txReceipt = _txReceipt;
		transactions[_tx_id].messages = _messages;
		for (uint i = 0; i < _messages.length; i++) {
			if (_messages[i].onAcceptance) {
				transactions[_tx_id].onAcceptanceMessages = true;
				break;
			}
		}
	}

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external onlyGenConsensus {
		transactions[_tx_id].validators.push(_validator);
		transactions[_tx_id].validatorVotesHash.push(_commitHash);
		validatorIndexInTx[_tx_id][_validator] = transactions[_tx_id]
			.validators
			.length;
	}

	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		ITransactions.VoteType _voteType,
		address _validator
	)
		external
		onlyGenConsensus
		returns (bool isLastVote, ITransactions.ResultType majorVoted)
	{
		uint votesRevealed = transactions[_tx_id].validatorVotes.length;
		uint validatorIndex = validatorIndexInTx[_tx_id][_validator] > 0
			? validatorIndexInTx[_tx_id][_validator] - 1
			: 0;
		if (
			transactions[_tx_id].validators[validatorIndex] == _validator &&
			transactions[_tx_id].validatorVotesHash[validatorIndex] == _voteHash
		) {
			if (votesRevealed > 0 && votesRevealed > validatorIndex) {
				revert VoteAlreadyCommitted();
			} else {
				transactions[_tx_id].validatorVotes.push(_voteType);
			}
		}
		isLastVote =
			transactions[_tx_id].validatorVotes.length ==
			transactions[_tx_id].validators.length;
		majorVoted = ITransactions.ResultType(0);
		if (isLastVote) {
			majorVoted = _getMajorityVote(_tx_id);
			transactions[_tx_id].result = majorVoted;
			transactions[_tx_id].lastVoteTimestamp = block.timestamp;
		}
	}

	function _getMajorityVote(
		bytes32 _tx_id
	) private view returns (ITransactions.ResultType result) {
		result = ITransactions.ResultType.Idle;
		uint validatorCount = transactions[_tx_id].validators.length;
		uint[] memory voteCounts = new uint[](
			uint(type(ITransactions.VoteType).max) + 1
		);
		for (uint i = 0; i < transactions[_tx_id].validatorVotes.length; i++) {
			voteCounts[uint(transactions[_tx_id].validatorVotes[i])]++;
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

	function getTransaction(
		bytes32 txId
	) external view returns (ITransactions.Transaction memory) {
		return transactions[txId];
	}

	function getTransactionLastVoteTimestamp(
		bytes32 txId
	) external view returns (uint256) {
		return transactions[txId].lastVoteTimestamp;
	}

	function _calculateMinAppealBond(
		bytes32 _tx_id
	) internal view returns (uint256 minAppealBond) {
		// TODO: Implement the logic to calculate the minimum appeal bond
		minAppealBond = 0;
	}

	function setGenConsensus(address _genConsensus) external onlyOwner {
		genConsensus = _genConsensus;
		emit GenConsensusSet(_genConsensus);
	}

	function setRandomSeed(
		bytes32 txId,
		bytes32 randomSeed
	) external onlyGenConsensus {
		transactions[txId].randomSeed = randomSeed;
	}

	function setActivationTimestamp(
		bytes32 txId,
		uint256 timestamp
	) external onlyGenConsensus {
		transactions[txId].activationTimestamp = timestamp;
	}

	modifier onlyGenConsensus() {
		if (msg.sender != genConsensus) {
			revert CallerNotConsensus();
		}
		_;
	}
}