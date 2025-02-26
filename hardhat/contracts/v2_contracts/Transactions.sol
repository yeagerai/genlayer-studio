// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IMessages.sol";
import "./utils/Errors.sol";
import "./interfaces/IGenStaking.sol";

contract Transactions is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	// Rounds of validators per round
	// normal rounds are VALIDATORS_PER_ROUND[2n+1], n = 0, 1, 2, 3, ...
	// appeal rounds are VALIDATORS_PER_ROUND[2n], n = 1, 2, 3, ...
	uint[] public VALIDATORS_PER_ROUND = [
		5,
		7,
		11,
		13,
		23,
		25,
		47,
		49,
		95,
		97,
		191,
		193,
		383,
		385,
		767,
		769,
		1535,
		1537
	];

	mapping(bytes32 => ITransactions.Transaction) public transactions;

	address public genConsensus;
	IGenStaking public genStaking;
	event GenConsensusSet(address indexed genConsensus);

	modifier onlyGenConsensus() {
		if (msg.sender != genConsensus) {
			revert Errors.CallerNotConsensus();
		}
		_;
	}

	function initialize(address _genConsensus) public initializer {
		__Ownable2Step_init();
		__Ownable_init(msg.sender);
		__ReentrancyGuard_init();
		__AccessControl_init();
		genConsensus = _genConsensus;
	}

	receive() external payable {}

	function getTransactionRecipient(
		bytes32 txId
	) external view returns (address recipient) {
		recipient = transactions[txId].recipient;
	}

	function getTransaction(
		bytes32 txId
	) external view returns (ITransactions.Transaction memory) {
		return transactions[txId];
	}

	function hasMessagesOnFinalization(
		bytes32 _tx_id
	) external view returns (bool itHasMessagesOnFinalization) {
		itHasMessagesOnFinalization = transactions[_tx_id].messages.length > 0;
	}

	function getMessagesForTransaction(
		bytes32 _tx_id
	) external view returns (IMessages.SubmittedMessage[] memory) {
		return transactions[_tx_id].messages;
	}

	function addNewTransaction(
		bytes32 txId,
		ITransactions.Transaction memory newTx
	) external onlyGenConsensus returns (bytes32) {
		transactions[txId] = newTx;
		return txId;
	}

	function activateTransaction(
		bytes32 _txId,
		address _activator,
		bytes32 _randomSeed
	)
		external
		returns (
			address recepient,
			uint256 leaderIndex,
			address[] memory validators
		)
	{
		ITransactions.TransactionStatus status = transactions[_txId].status;
		if (status != ITransactions.TransactionStatus.Pending) {
			revert Errors.TransactionNotPending();
		}
		transactions[_txId].status = ITransactions.TransactionStatus.Proposing;
		uint round = transactions[_txId].roundData.length > 0
			? transactions[_txId].roundData.length - 1
			: 0;
		if (round == 0) {
			_checkActivator(_txId, _activator);
		}
		(validators, leaderIndex) = _createNewRound(
			_txId,
			round,
			0,
			_randomSeed,
			2,
			false
		);
		transactions[_txId].activationTimestamp = block.timestamp;
		transactions[_txId].randomSeed = _randomSeed;
		transactions[_txId].status = ITransactions.TransactionStatus.Proposing;
		recepient = transactions[_txId].recipient;
	}

	function proposeTransactionReceipt(
		bytes32 _tx_id,
		address _leader,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages
	)
		external
		onlyGenConsensus
		returns (
			address recipient,
			bool leaderTimeout,
			address newLeader,
			uint round
		)
	{
		if (_leader != _getLatestRoundLeader(_tx_id)) {
			revert Errors.CallerNotLeader();
		}
		if (
			transactions[_tx_id].status !=
			ITransactions.TransactionStatus.Proposing
		) {
			revert Errors.TransactionNotProposing();
		}
		round = transactions[_tx_id].roundData.length - 1;
		if (_txReceipt.length == 0) {
			uint256 rotations = transactions[_tx_id]
				.roundData[round]
				.rotationsLeft;
			if (rotations == 0) {
				transactions[_tx_id].status = ITransactions
					.TransactionStatus
					.Undetermined;
			} else {
				newLeader = _rotateLeader(_tx_id, round, rotations);
			}
			leaderTimeout = true;
		} else {
			transactions[_tx_id].status = ITransactions
				.TransactionStatus
				.Committing;
			transactions[_tx_id].txReceipt = _txReceipt;
			transactions[_tx_id].messages = _messages;
			for (uint i = 0; i < _messages.length; i++) {
				if (_messages[i].onAcceptance) {
					transactions[_tx_id].onAcceptanceMessages = true;
					break;
				}
			}
		}
		recipient = transactions[_tx_id].recipient;
	}

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		address _validator
	) external onlyGenConsensus returns (bool isLastVote) {
		uint round = transactions[_tx_id].roundData.length - 1;
		ITransactions.RoundData memory roundData = transactions[_tx_id]
			.roundData[round];
		ITransactions.TransactionStatus status = transactions[_tx_id].status;
		uint votesCommitted = ++transactions[_tx_id]
			.roundData[round]
			.votesCommitted;
		if (votesCommitted == roundData.roundValidators.length) {
			isLastVote = true;
			transactions[_tx_id].status = round % 2 == 0
				? ITransactions.TransactionStatus.Revealing
				: ITransactions.TransactionStatus.AppealRevealing;
		} else if (votesCommitted > roundData.roundValidators.length) {
			revert Errors.VoteAlreadyCommitted();
		}
		_checkStatusCommittedOrRevealed(round, status, true);
		// Get validator index in current round validators array
		(uint validatorIndex, bool isFirstValidator) = _getValidatorIndex(
			_tx_id,
			round,
			_validator
		);
		if (validatorIndex == 0 && !isFirstValidator) {
			revert Errors.ValidValidatorNotFound();
		}
		if (
			transactions[_tx_id].roundData[round].validatorVotesHash[
				validatorIndex
			] != bytes32(0)
		) {
			revert Errors.VoteAlreadyCommitted();
		}
		transactions[_tx_id].roundData[round].validatorVotesHash[
			validatorIndex
		] = _commitHash;
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
			address recipient,
			uint round,
			bool hasMessagesOnAcceptance,
			uint rotationsLeft,
			ITransactions.NewRoundData memory newRoundData
		)
	{
		round = transactions[_tx_id].roundData.length - 1;
		ITransactions.RoundData memory roundData = transactions[_tx_id]
			.roundData[round];
		ITransactions.TransactionStatus status = transactions[_tx_id].status;
		_checkStatusCommittedOrRevealed(round, status, false);
		uint votesRevealed = ++transactions[_tx_id]
			.roundData[round]
			.votesRevealed;
		if (votesRevealed == roundData.roundValidators.length) {
			isLastVote = true;
		} else if (votesRevealed > roundData.roundValidators.length) {
			revert Errors.VoteAlreadyRevealed();
		}
		(uint validatorIndex, bool isFirstValidator) = _getValidatorIndex(
			_tx_id,
			round,
			_validator
		);
		if (validatorIndex == 0 && !isFirstValidator) {
			revert Errors.ValidValidatorNotFound();
		}
		if (roundData.validatorVotesHash[validatorIndex] != _voteHash) {
			revert Errors.InvalidVote();
		}
		transactions[_tx_id].roundData[round].validatorVotes[
			validatorIndex
		] = _voteType;
		majorVoted = ITransactions.ResultType(0);
		if (isLastVote) {
			majorVoted = _getMajorityVote(
				transactions[_tx_id].roundData[round]
			);
			transactions[_tx_id].roundData[round].result = majorVoted;
			if (
				majorVoted == ITransactions.ResultType.MajorityAgree ||
				majorVoted == ITransactions.ResultType.Agree
			) {
				if (round % 2 == 0) {
					transactions[_tx_id].status = ITransactions
						.TransactionStatus
						.Accepted;
					hasMessagesOnAcceptance = transactions[_tx_id]
						.onAcceptanceMessages;
				} else {
					transactions[_tx_id].status = transactions[_tx_id]
						.previousStatus;
					transactions[_tx_id].previousStatus = ITransactions
						.TransactionStatus
						.AppealRevealing;
				}
			} else {
				if (round % 2 == 0) {
					transactions[_tx_id].status = ITransactions
						.TransactionStatus
						.Undetermined;
				} else {
					// Successfully appealed
					transactions[_tx_id].status = ITransactions
						.TransactionStatus
						.Proposing;
					(
						newRoundData.roundValidators,
						newRoundData.leaderIndex
					) = _createNewRound(
						_tx_id,
						round + 1,
						0,
						transactions[_tx_id].randomSeed,
						2,
						false
					);
					newRoundData.round = round + 1;
				}
			}
			transactions[_tx_id].lastVoteTimestamp = block.timestamp;
		}
		recipient = transactions[_tx_id].recipient;
		rotationsLeft = transactions[_tx_id].roundData[round].rotationsLeft;
	}

	function finalizeTransaction(
		bytes32 _tx_id
	) external returns (address recipient, uint256 lastVoteTimestamp) {
		ITransactions.TransactionStatus status = transactions[_tx_id].status;
		if (
			status != ITransactions.TransactionStatus.Accepted &&
			status != ITransactions.TransactionStatus.Undetermined
		) {
			revert Errors.TransactionNotAcceptedOrUndetermined();
		}
		transactions[_tx_id].status = ITransactions.TransactionStatus.Finalized;
		recipient = transactions[_tx_id].recipient;
		lastVoteTimestamp = transactions[_tx_id].lastVoteTimestamp;
	}

	function cancelTransaction(
		bytes32 _tx_id,
		address _sender
	) external onlyGenConsensus returns (address recipient) {
		if (
			transactions[_tx_id].status !=
			ITransactions.TransactionStatus.Pending
		) {
			revert Errors.TransactionNotPending();
		}
		if (transactions[_tx_id].sender != _sender) {
			revert Errors.CallerNotSender();
		}
		transactions[_tx_id].status = ITransactions.TransactionStatus.Canceled;
		recipient = transactions[_tx_id].recipient;
	}

	function submitAppeal(
		bytes32 _tx_id,
		uint256 _appealBond
	) external returns (address[] memory appealValidators, uint round) {
		round = transactions[_tx_id].roundData.length - 1;
		// bool lastRoundLeaderTimeout = transactions[_tx_id].txReceipt.length ==
		// 	0;
		ITransactions.TransactionStatus status = transactions[_tx_id].status;
		if (
			status != ITransactions.TransactionStatus.Undetermined &&
			status != ITransactions.TransactionStatus.Accepted
		) {
			revert Errors.CanNotAppeal();
		}
		if (round % 2 == 1) {
			_createAnEmptyRound(_tx_id);
			round++;
		}
		if (
			// !lastRoundLeaderTimeout &&
			_appealBond < _calculateMinAppealBond(_tx_id, round + 1)
		) {
			revert Errors.AppealBondTooLow();
		}
		(appealValidators, ) = _createNewRound(
			_tx_id,
			round + 1,
			_appealBond,
			transactions[_tx_id].randomSeed,
			2,
			false
		);
		transactions[_tx_id].consumedValidators = _concatArraysAndDropIndex(
			transactions[_tx_id].consumedValidators,
			appealValidators,
			transactions[_tx_id].consumedValidators.length
		);
		transactions[_tx_id].previousStatus = transactions[_tx_id].status;
		transactions[_tx_id].status = ITransactions
			.TransactionStatus
			.AppealCommitting;
		++round;
	}

	function rotateLeader(
		bytes32 txId
	) external onlyGenConsensus returns (address newLeader) {
		uint256 round = transactions[txId].roundData.length - 1;
		uint256 rotationsLeft = transactions[txId]
			.roundData[round]
			.rotationsLeft;
		if (rotationsLeft == 0) {
			revert Errors.NoRotationsLeft();
		}
		newLeader = _rotateLeader(txId, round, rotationsLeft);
	}

	function _rotateLeader(
		bytes32 txId,
		uint256 round,
		uint256 rotationsLeft
	) internal returns (address newLeader) {
		(address[] memory newValidators, uint256 leaderIndex) = _createNewRound(
			txId,
			round,
			0,
			transactions[txId].randomSeed,
			rotationsLeft - 1,
			true
		);
		--transactions[txId].roundData[round].rotationsLeft;
		newLeader = newValidators[leaderIndex];
		transactions[txId].status = ITransactions.TransactionStatus.Proposing;
	}

	function _getValidatorIndex(
		bytes32 _txId,
		uint256 _round,
		address _validator
	) internal view returns (uint256 validatorIndex, bool isFirstValidator) {
		for (
			uint256 i = 0;
			i < transactions[_txId].roundData[_round].roundValidators.length;
			i++
		) {
			if (
				transactions[_txId].roundData[_round].roundValidators[i] ==
				_validator
			) {
				validatorIndex = i;
				isFirstValidator = i == 0;
				break;
			}
		}
	}

	function _getMajorityVote(
		ITransactions.RoundData memory roundData
	) internal pure returns (ITransactions.ResultType result) {
		result = ITransactions.ResultType.Idle;
		uint validatorCount = roundData.roundValidators.length;
		uint[] memory voteCounts = new uint[](
			uint(type(ITransactions.VoteType).max) + 1
		);
		for (uint i = 0; i < roundData.validatorVotes.length; i++) {
			voteCounts[uint(roundData.validatorVotes[i])]++;
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

	function _getLatestRoundLeader(
		bytes32 txId
	) private view returns (address) {
		uint latestRound = transactions[txId].roundData.length - 1;
		ITransactions.RoundData memory roundData = transactions[txId].roundData[
			latestRound
		];
		return roundData.roundValidators[roundData.leaderIndex];
	}

	function _createNewRound(
		bytes32 _tx_id,
		uint256 _round,
		uint256 _appealBond,
		bytes32 _randomSeed,
		uint256 _rotationsLeft,
		bool isRotation
	) internal returns (address[] memory roundValidators, uint256 leaderIndex) {
		if (isRotation) {
			(roundValidators, leaderIndex) = _getValidatorsAndLeaderIndex(
				_randomSeed,
				1,
				transactions[_tx_id].consumedValidators
			);
			transactions[_tx_id].consumedValidators.push(roundValidators[0]);
			roundValidators = _concatArraysAndDropIndex(
				transactions[_tx_id].roundData[_round].roundValidators,
				roundValidators,
				transactions[_tx_id].roundData[_round].leaderIndex
			);
			leaderIndex = _randomlySelectLeaderIndex(
				_randomSeed,
				transactions[_tx_id].consumedValidators.length,
				roundValidators.length,
				leaderIndex
			);
			transactions[_tx_id].roundData[_round] = ITransactions.RoundData(
				_round,
				leaderIndex,
				0,
				0,
				_appealBond,
				_rotationsLeft,
				ITransactions.ResultType(0),
				roundValidators,
				new bytes32[](roundValidators.length),
				new ITransactions.VoteType[](roundValidators.length)
			);
		} else {
			if (_round % 2 == 0 && _round > 0) {
				address[] memory missingValidators;
				(
					roundValidators,
					missingValidators
				) = _getPreviousRoundValidators(_tx_id, _round, _randomSeed);
				transactions[_tx_id]
					.consumedValidators = _concatArraysAndDropIndex(
					transactions[_tx_id].consumedValidators,
					missingValidators,
					transactions[_tx_id].consumedValidators.length
				);
				leaderIndex = _randomlySelectLeaderIndex(
					_randomSeed,
					transactions[_tx_id].consumedValidators.length,
					roundValidators.length,
					leaderIndex
				);
			} else {
				(roundValidators, leaderIndex) = _getValidatorsAndLeaderIndex(
					_randomSeed,
					VALIDATORS_PER_ROUND[_round],
					transactions[_tx_id].consumedValidators
				);
				transactions[_tx_id]
					.consumedValidators = _concatArraysAndDropIndex(
					transactions[_tx_id].consumedValidators,
					roundValidators,
					transactions[_tx_id].consumedValidators.length
				);
			}
			// Set the round data
			// Resets in case of rotation
			transactions[_tx_id].roundData.push(
				ITransactions.RoundData(
					_round,
					leaderIndex,
					0,
					0,
					_appealBond,
					_rotationsLeft,
					ITransactions.ResultType(0),
					roundValidators,
					new bytes32[](roundValidators.length),
					new ITransactions.VoteType[](roundValidators.length)
				)
			);
		}
	}

	function _createAnEmptyRound(bytes32 _tx_id) internal {
		transactions[_tx_id].roundData.push(
			ITransactions.RoundData(
				0,
				0,
				0,
				0,
				0,
				0,
				ITransactions.ResultType(0),
				new address[](0),
				new bytes32[](0),
				new ITransactions.VoteType[](0)
			)
		);
	}

	function _getPreviousRoundValidators(
		bytes32 _tx_id,
		uint256 _round,
		bytes32 _randomSeed
	)
		internal
		view
		returns (
			address[] memory previousRoundValidators,
			address[] memory missingValidators
		)
	{
		uint256 previousRoundValidatorsLength = transactions[_tx_id]
			.roundData[_round - 2]
			.roundValidators
			.length;
		if (previousRoundValidatorsLength > 0) {
			previousRoundValidators = _concatArraysAndDropIndex(
				transactions[_tx_id].roundData[_round - 2].roundValidators,
				transactions[_tx_id].roundData[_round - 1].roundValidators,
				transactions[_tx_id].roundData[_round - 2].leaderIndex
			);
		} else {
			uint validPreviousRound = 0;
			for (uint256 i = _round - 2; i > 0; i - 2) {
				if (
					transactions[_tx_id].roundData[i].roundValidators.length > 0
				) {
					validPreviousRound = i;
					break;
				}
			}
			uint256 missingValidatorsLength = VALIDATORS_PER_ROUND[_round] -
				transactions[_tx_id]
					.roundData[validPreviousRound]
					.roundValidators
					.length -
				transactions[_tx_id]
					.roundData[_round - 1]
					.roundValidators
					.length;
			(missingValidators, ) = _getValidatorsAndLeaderIndex(
				_randomSeed,
				missingValidatorsLength,
				transactions[_tx_id].consumedValidators
			);
			previousRoundValidators = _concatArraysAndDropIndex(
				transactions[_tx_id]
					.roundData[validPreviousRound]
					.roundValidators,
				transactions[_tx_id].roundData[_round - 1].roundValidators,
				transactions[_tx_id].roundData[validPreviousRound].leaderIndex
			);
			previousRoundValidators = _concatArraysAndDropIndex(
				previousRoundValidators,
				missingValidators,
				previousRoundValidators.length
			);
		}
	}

	function _calculateMinAppealBond(
		bytes32 _tx_id,
		uint256 _round
	) internal view returns (uint256 minAppealBond) {
		// TODO: Implement the logic to calculate the minimum appeal bond
		minAppealBond = 0;
	}

	function _concatArraysAndDropIndex(
		address[] memory _array1,
		address[] memory _array2,
		uint256 _indexToDrop
	) internal pure returns (address[] memory result) {
		uint256 reduceLength = _array1.length > 0 &&
			_indexToDrop < _array1.length
			? 1
			: 0;
		result = new address[](_array1.length + _array2.length - reduceLength);
		uint resultIndex = 0;
		for (uint i = 0; i < _array1.length; i++) {
			if (i != _indexToDrop) {
				result[resultIndex] = _array1[i];
				resultIndex++;
			}
		}
		for (uint i = 0; i < _array2.length; i++) {
			result[resultIndex] = _array2[i];
			resultIndex++;
		}
	}

	function _randomlySelectLeaderIndex(
		bytes32 _randomSeed,
		uint256 _consumedValidatorsLength,
		uint256 _roundValidatorsLength,
		uint256 _addedRandomness
	) internal pure returns (uint256 leaderIndex) {
		leaderIndex =
			uint256(
				keccak256(
					abi.encodePacked(
						_randomSeed,
						_consumedValidatorsLength,
						_addedRandomness
					)
				)
			) %
			_roundValidatorsLength;
	}

	function _checkActivator(bytes32 _txId, address _activator) internal view {
		if (transactions[_txId].activator != _activator) {
			revert Errors.CallerNotActivator();
		}
		// TODO: Check if it is the next activator
	}

	function _checkStatusCommittedOrRevealed(
		uint round,
		ITransactions.TransactionStatus status,
		bool checkCommitted
	) internal pure {
		bool isRegularRound = round % 2 == 0;
		if (checkCommitted) {
			if (isRegularRound) {
				// regular round
				if (status != ITransactions.TransactionStatus.Committing) {
					revert Errors.TransactionNotCommitting();
				}
			} else {
				// appeal round
				if (
					status != ITransactions.TransactionStatus.AppealCommitting
				) {
					revert Errors.TransactionNotAppealCommitting();
				}
			}
		} else {
			if (isRegularRound) {
				// regular round
				if (status != ITransactions.TransactionStatus.Revealing) {
					revert Errors.TransactionNotRevealing();
				}
			} else {
				// appeal round
				if (status != ITransactions.TransactionStatus.AppealRevealing) {
					revert Errors.TransactionNotAppealRevealing();
				}
			}
		}
	}

	function _getValidatorsAndLeaderIndex(
		bytes32 _randomSeed,
		uint256 numValidators,
		address[] memory consumedValidators
	) internal view returns (address[] memory validators, uint256 leaderIndex) {
		(validators, leaderIndex) = genStaking.getValidatorsForTx(
			_randomSeed,
			numValidators,
			consumedValidators
		);
	}

	function setGenConsensus(address _genConsensus) external onlyOwner {
		genConsensus = _genConsensus;
		emit GenConsensusSet(_genConsensus);
	}

	function setGenStaking(address _genStaking) external onlyOwner {
		genStaking = IGenStaking(_genStaking);
	}
}