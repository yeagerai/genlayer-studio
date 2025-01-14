// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/IGenManager.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IQueues.sol";
import "./interfaces/IGhostFactory.sol";
import "./interfaces/IGenStaking.sol";
import "./interfaces/IMessages.sol";
import "./interfaces/IAppeals.sol";
import "../RandomnessUtils.sol";
import "./utils/Errors.sol";
/**
 * @title ConsensusMain
 * @notice Main contract for managing transaction consensus and validation in the Genlayer protocol
 * @dev Handles transaction lifecycle, issues messages, manages appeals, and handles fees
 */
contract ConsensusMain is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
	bytes32 public constant VALIDATOR_ROLE = keccak256("VALIDATOR_ROLE");

	uint256 public ACCEPTANCE_TIMEOUT;
	uint256 public ACTIVATION_TIMEOUT;

	IGenManager public genManager;
	ITransactions public genTransactions;
	IQueues public genQueue;
	IGhostFactory public ghostFactory;
	IGenStaking public genStaking;
	IMessages public genMessages;
	IAppeals public genAppeals;

	mapping(bytes32 => ITransactions.TransactionStatus) public txStatus;
	mapping(address => bool) public ghostContracts;
	mapping(bytes32 => address) public txActivator;
	mapping(bytes32 => uint) public txLeaderIndex;
	mapping(bytes32 => address[]) public validatorsForTx;
	mapping(bytes32 => mapping(address => bool)) public validatorIsActiveForTx;
	mapping(bytes32 => mapping(address => bool)) public voteCommittedForTx;
	mapping(bytes32 => uint) public voteCommittedCountForTx;
	mapping(bytes32 => mapping(address => bool)) public voteRevealedForTx;
	mapping(bytes32 => uint) public voteRevealedCountForTx;
	mapping(address => bytes32) public recipientRandomSeed;

	receive() external payable {}

	/**
	 * @notice Initializes the contract
	 * @param _genManager Address of the Gen Manager contract
	 */
	function initialize(address _genManager) public initializer {
		__Ownable2Step_init();
		__Ownable_init(msg.sender);
		__ReentrancyGuard_init();
		__AccessControl_init();
		genManager = IGenManager(_genManager);
	}

	// EXTERNAL FUNCTIONS - STATE CHANGING

	/**
	 * @notice Adds a new transaction to the system
	 * @param _sender Transaction sender address
	 * @param _recipient Recipient GenVM contract address
	 * @param _numOfInitialValidators Number of validators to assign
	 * @param _maxRotations Maximum number of leader rotations allowed
	 * @param _txData Transaction data to be executed
	 */
	function addTransaction(
		address _sender,
		address _recipient,
		uint256 _numOfInitialValidators,
		uint256 _maxRotations,
		bytes memory _txData
	) external {
		_addTransaction(
			_sender,
			_recipient,
			_numOfInitialValidators,
			_maxRotations,
			_txData
		);
		// TODO: Fee verification handling
	}

	/**
	 * @notice Activates a pending transaction by updating its random seed and moving it to the active state
	 * @dev Only callable by the designated activator for the transaction
	 * @param _tx_id The unique identifier of the transaction to activate
	 * @param _vrfProof Verifiable random function proof used to update the random seed
	 * @custom:throws TransactionNotAtPendingQueueHead if transaction is not at the head of pending queue
	 * @custom:emits TransactionActivated when transaction is successfully activated
	 */
	function activateTransaction(
		bytes32 _tx_id,
		bytes calldata _vrfProof
	) external onlyActivator(_tx_id) {
		ITransactions.ActivationInfo memory _activationInfo = genTransactions
			.getTransactionActivationInfo(_tx_id);
		if (
			!genQueue.isAtPendingQueueHead(
				_activationInfo.recepientAddress,
				_tx_id
			)
		) {
			revert Errors.TransactionNotAtPendingQueueHead();
		}
		bytes32 randomSeed = recipientRandomSeed[
			_activationInfo.recepientAddress
		];
		randomSeed = bytes32(
			RandomnessUtils.updateRandomSeed(
				_vrfProof,
				uint256(randomSeed),
				msg.sender
			)
		);
		// update recipient randomSeed
		recipientRandomSeed[_activationInfo.recepientAddress] = randomSeed;
		_activateTransaction(_tx_id, _activationInfo, randomSeed);
	}

	/**
	 * @notice Proposes a transaction receipt and associated messages for a transaction
	 * @dev Only callable by the current leader validator for the transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @param _txReceipt The execution receipt/result of the transaction
	 * @param _messages Array of messages to be emitted as part of the transaction
	 * @param _vrfProof Verifiable random function proof used to update the random seed
	 * @custom:throws TransactionNotProposing if transaction is not in Proposing state
	 * @custom:emits TransactionReceiptProposed when receipt is successfully proposed
	 */
	function proposeReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages,
		bytes calldata _vrfProof
	) external onlyLeader(_tx_id) {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Proposing) {
			revert Errors.TransactionNotProposing();
		}
		ITransactions.ActivationInfo memory _activationInfo = genTransactions
			.getTransactionActivationInfo(_tx_id);
		bytes32 randomSeed = recipientRandomSeed[
			_activationInfo.recepientAddress
		];
		randomSeed = bytes32(
			RandomnessUtils.updateRandomSeed(
				_vrfProof,
				uint256(randomSeed),
				msg.sender
			)
		);
		// update recipient randomSeed
		recipientRandomSeed[_activationInfo.recepientAddress] = randomSeed;
		txStatus[_tx_id] = ITransactions.TransactionStatus.Committing;
		genTransactions.proposeTransactionReceipt(
			_tx_id,
			_txReceipt,
			_messages
		);

		emit TransactionReceiptProposed(_tx_id);
	}

	/**
	 * @notice Commits a vote for a transaction
	 * @dev Only callable by a validator for the transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @param _commitHash The hash of the vote to commit
	 * @param _isAppeal Whether the vote is an appeal
	 * @custom:throws TransactionNotAppealCommitting if transaction is not in AppealCommitting state
	 * @custom:throws TransactionNotCommitting if transaction is not in Committing state
	 * @custom:throws VoteAlreadyCommitted if the validator has already committed a vote
	 * @custom:emits VoteCommitted when vote is successfully committed
	 */
	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		bool _isAppeal
	) external onlyValidator(_tx_id) {
		if (_isAppeal) {
			if (
				txStatus[_tx_id] !=
				ITransactions.TransactionStatus.AppealCommitting
			) {
				revert Errors.TransactionNotAppealCommitting();
			}

			bool isLastVote = genAppeals.commitVote(
				_tx_id,
				_commitHash,
				msg.sender
			);
			if (isLastVote) {
				txStatus[_tx_id] = ITransactions
					.TransactionStatus
					.AppealRevealing;
			}
		} else {
			if (
				txStatus[_tx_id] != ITransactions.TransactionStatus.Committing
			) {
				revert Errors.TransactionNotCommitting();
			}
			if (voteCommittedForTx[_tx_id][msg.sender]) {
				revert Errors.VoteAlreadyCommitted();
			}
			voteCommittedForTx[_tx_id][msg.sender] = true;
			genTransactions.commitVote(_tx_id, _commitHash, msg.sender);
			voteCommittedCountForTx[_tx_id]++;
			bool isLastVote = voteCommittedCountForTx[_tx_id] ==
				validatorsForTx[_tx_id].length;
			if (isLastVote) {
				txStatus[_tx_id] = ITransactions.TransactionStatus.Revealing;
			}
			emit VoteCommitted(_tx_id, msg.sender, isLastVote);
		}
	}

	/**
	 * @notice Reveals a vote for a transaction
	 * @dev Only callable by a validator for the transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @param _voteHash The hash of the vote to reveal
	 * @param _voteType The type of the vote
	 * @param _nonce The nonce used for the vote
	 * @param _isAppeal Whether the vote is an appeal
	 * @custom:throws TransactionNotAppealRevealing if transaction is not in AppealRevealing state
	 * @custom:throws TransactionNotRevealing if transaction is not in Revealing state
	 * @custom:throws InvalidVote if the revealed vote is invalid
	 * @custom:emits VoteRevealed when vote is successfully revealed
	 */
	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		ITransactions.VoteType _voteType,
		uint _nonce,
		bool _isAppeal
	) external onlyValidator(_tx_id) {
		if (_isAppeal) {
			if (
				txStatus[_tx_id] !=
				ITransactions.TransactionStatus.AppealRevealing
			) {
				revert Errors.TransactionNotAppealRevealing();
			}
			(
				bool isLastVote,
				ITransactions.ResultType appealResult,
				ITransactions.TransactionStatus originalStatus
			) = genAppeals.revealVote(_tx_id, _voteHash, _voteType, msg.sender);
			if (isLastVote) {
				ITransactions.ResultType originalResult = genTransactions
					.getTransactionResult(_tx_id);
				if (_sameResult(originalResult, appealResult)) {
					txStatus[_tx_id] = originalStatus;
				} else {
					txStatus[_tx_id] = ITransactions.TransactionStatus.Pending;
					ITransactions.ActivationInfo
						memory _activationInfo = genTransactions
							.getTransactionActivationInfo(_tx_id);
					// revert the transaction and add to the pending queue
					(, bytes32[] memory txsForRecomputation) = genQueue
						.addTransactionToPendingQueue(
							_activationInfo.recepientAddress,
							_tx_id
						);
					_activateTransaction(
						_tx_id,
						_activationInfo,
						recipientRandomSeed[_activationInfo.recepientAddress]
					);
					emit TransactionNeedsRecomputation(txsForRecomputation);
				}
			}
		} else {
			ITransactions.ActivationInfo
				memory _activationInfo = genTransactions
					.getTransactionActivationInfo(_tx_id);
			if (txStatus[_tx_id] != ITransactions.TransactionStatus.Revealing) {
				revert Errors.TransactionNotRevealing();
			}
			if (voteRevealedForTx[_tx_id][msg.sender]) {
				revert Errors.VoteAlreadyRevealed();
			}
			if (
				keccak256(abi.encodePacked(msg.sender, _voteType, _nonce)) !=
				_voteHash
			) {
				revert Errors.InvalidVote();
			}
			voteRevealedForTx[_tx_id][msg.sender] = true;
			voteRevealedCountForTx[_tx_id]++;
			(bool isLastVote, ITransactions.ResultType result) = genTransactions
				.revealVote(_tx_id, _voteHash, _voteType, msg.sender);
			if (isLastVote) {
				if (
					result == ITransactions.ResultType.MajorityAgree ||
					result == ITransactions.ResultType.Agree
				) {
					txStatus[_tx_id] = ITransactions.TransactionStatus.Accepted;
					genQueue.addTransactionToAcceptedQueue(
						_activationInfo.recepientAddress,
						_tx_id
					);
					emit TransactionAccepted(_tx_id);

					// Process on-acceptance messages
					if (genTransactions.hasOnAcceptanceMessages(_tx_id)) {
						_processMessages(_tx_id, true); // true for acceptance phase
					}
				} else {
					if (_activationInfo.rotationsLeft > 0) {
						// (more rounds of rotations) Rotate
						// TODO: check also gas limit
						_rotateLeader(_tx_id);
					} else {
						txStatus[_tx_id] = ITransactions
							.TransactionStatus
							.Undetermined;
						genQueue.addTransactionToUndeterminedQueue(
							_activationInfo.recepientAddress,
							_tx_id
						);
					}
				}
			}
			emit VoteRevealed(
				_tx_id,
				msg.sender,
				_voteType,
				isLastVote,
				result
			);
		}
	}

	/**
	 * @notice Finalizes a transaction
	 * @dev Only callable by the transaction recipient
	 * @param _tx_id The unique identifier of the transaction
	 * @custom:throws TransactionNotAcceptedOrUndetermined if transaction is not in Accepted or Undetermined state
	 * @custom:emits TransactionFinalized when transaction is successfully finalized
	 */
	function finalizeTransaction(bytes32 _tx_id) external {
		if (
			txStatus[_tx_id] != ITransactions.TransactionStatus.Accepted &&
			txStatus[_tx_id] != ITransactions.TransactionStatus.Undetermined
		) {
			revert Errors.TransactionNotAcceptedOrUndetermined();
		}
		ITransactions.ActivationInfo memory _activationInfo = genTransactions
			.getTransactionActivationInfo(_tx_id);

		if (
			!genQueue.isAtFinalizedQueueHead(
				_activationInfo.recepientAddress,
				_tx_id
			)
		) {
			revert Errors.FinalizationNotAllowed();
		}
		uint lastVoteTimestamp = genTransactions
			.getTransactionLastVoteTimestamp(_tx_id);
		genQueue.addTransactionToFinalizedQueue(
			_activationInfo.recepientAddress,
			_tx_id
		);
		if (block.timestamp - lastVoteTimestamp > ACCEPTANCE_TIMEOUT) {
			txStatus[_tx_id] = ITransactions.TransactionStatus.Finalized;
			if (genTransactions.hasMessagesOnFinalization(_tx_id)) {
				_processMessages(_tx_id, false); // false for finalization phase
			}
			emit TransactionFinalized(_tx_id);
		}
	}

	/**
	 * @notice Submits an appeal for a transaction
	 * @dev Only callable by a validator for the transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @custom:throws CanNotAppeal if the appeal cannot be submitted
	 * @custom:emits AppealStarted when appeal is successfully started
	 */
	function submitAppeal(bytes32 _tx_id) external payable {
		IQueues.LastQueueModification memory lastQueueModification = genQueue
			.getLastQueueModification(_tx_id);
		if (
			lastQueueModification.lastQueueTimestamp > 0 &&
			block.timestamp <
			lastQueueModification.lastQueueTimestamp + ACTIVATION_TIMEOUT &&
			lastQueueModification.lastQueueType == IQueues.QueueType.Pending
		) {
			revert Errors.CanNotAppeal();
		}
		if (
			txStatus[_tx_id] != ITransactions.TransactionStatus.Undetermined &&
			txStatus[_tx_id] != ITransactions.TransactionStatus.Accepted
		) {
			revert Errors.CanNotAppeal();
		}
		(uint minBond, bytes32 randomSeed) = genTransactions.getAppealInfo(
			_tx_id
		);
		if (msg.value < minBond) {
			revert Errors.AppealBondTooLow();
		}
		ITransactions.TransactionStatus originalStatus = txStatus[_tx_id];
		txStatus[_tx_id] = ITransactions.TransactionStatus.AppealCommitting;
		// Select validators for appeal
		address[] memory consumedValidators = validatorsForTx[_tx_id];
		(address[] memory validators, ) = _getValidatorsAndLeaderIndex(
			randomSeed,
			consumedValidators.length + 2,
			consumedValidators
		);
		uint appealIndex = genAppeals.setAppealData(
			_tx_id,
			originalStatus,
			validators
		);
		emit AppealStarted(_tx_id, msg.sender, msg.value, appealIndex);
	}

	/**
	 * @notice Executes a message
	 * @dev Only callable by the messages contract or the owner
	 * @param _recipient The address of the recipient
	 * @param _value The value to be sent
	 * @param _data The data to be executed
	 * @return success - true if the message is successfully executed, false otherwise
	 */
	function executeMessage(
		address _recipient,
		uint _value,
		bytes memory _data
	) external returns (bool success) {
		if (msg.sender != address(genMessages) && msg.sender != owner()) {
			revert Errors.CallerNotMessages();
		}
		(success, ) = _recipient.call{ value: _value }(_data);
	}

	/**
	 * @notice Cancels a pending transaction
	 * @param _tx_id The unique identifier of the transaction to cancel
	 * @dev Only the original sender can cancel a pending transaction
	 * @custom:throws TransactionNotPending if transaction is not in pending state
	 * @custom:throws TransactionNotAtPendingQueueHead if transaction is not at the head of pending queue
	 * @custom:throws CallerNotSender if caller is not the original transaction sender
	 * @custom:emits TransactionCancelled when transaction is successfully cancelled
	 */
	function cancelTransaction(bytes32 _tx_id) external {
		// Check transaction status
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Pending) {
			revert Errors.TransactionNotPending();
		}

		// Get transaction info
		ITransactions.ActivationInfo memory _activationInfo = genTransactions
			.getTransactionActivationInfo(_tx_id);

		// Check if transaction is at the head of pending queue
		if (
			!genQueue.isAtPendingQueueHead(
				_activationInfo.recepientAddress,
				_tx_id
			)
		) {
			revert Errors.TransactionNotAtPendingQueueHead();
		}

		// Check if caller is the original sender
		if (msg.sender != _activationInfo.sender) {
			revert Errors.CallerNotSender();
		}

		// Remove transaction from pending queue
		genQueue.removeTransactionFromPendingQueue(
			_activationInfo.recepientAddress,
			_tx_id
		);

		// Update transaction status
		txStatus[_tx_id] = ITransactions.TransactionStatus.Canceled;

		emit TransactionCancelled(_tx_id, msg.sender);
	}

	// VIEW FUNCTIONS

	/**
	 * @notice Retrieves the number of validators for a transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @return The number of validators for the transaction
	 */
	function validatorsCountForTx(bytes32 _tx_id) external view returns (uint) {
		return validatorsForTx[_tx_id].length;
	}

	/**
	 * @notice Retrieves the validators for a transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @return The validators for the transaction
	 */
	function getValidatorsForTx(
		bytes32 _tx_id
	) external view returns (address[] memory) {
		return validatorsForTx[_tx_id];
	}

	// INTERNAL FUNCTIONS
	function _addTransaction(
		address _sender,
		address _recipient,
		uint256 _numOfInitialValidators,
		uint256 _maxRotations,
		bytes memory _txData
	) internal returns (bytes32 tx_id, address activator) {
		if (_sender == address(0)) {
			_sender = msg.sender;
		}
		bytes32 randomSeed = _recipient == address(0)
			? keccak256(abi.encodePacked(_sender))
			: recipientRandomSeed[_recipient];
		if (_recipient == address(0)) {
			// Contract deployment transaction
			ghostFactory.createGhost();
			address ghost = ghostFactory.latestGhost();
			_storeGhost(ghost);
			_recipient = ghost;
			// Initial random seed for the recipient account
			recipientRandomSeed[_recipient] = randomSeed;
		} else if (!ghostContracts[_recipient]) {
			revert Errors.NonGenVMContract();
		}
		// bytes32 randomSeed = recipientRandomSeed[_recipient]; // recipient randomSeed is used for activation
		(tx_id, activator) = _generateTx(
			_sender,
			_recipient,
			_numOfInitialValidators,
			_maxRotations,
			randomSeed,
			_txData
		);
		txActivator[tx_id] = activator;
		txStatus[tx_id] = ITransactions.TransactionStatus.Pending;
		emit NewTransaction(tx_id, _recipient, activator);
	}

	/**
	 * @notice Rotates the leader for a transaction
	 * @param _tx_id The unique identifier of the transaction
	 */
	function _rotateLeader(bytes32 _tx_id) internal {
		bytes32 _randomSeed = genTransactions.getTransactionSeed(_tx_id);
		// Reset voting state
		_resetVotes(_tx_id);
		genTransactions.resetVotes(_tx_id);
		// 1) one validator is removed
		address leader = validatorsForTx[_tx_id][txLeaderIndex[_tx_id]];
		genTransactions.rotateLeader(_tx_id, leader); // .push() to consumedValidators
		validatorIsActiveForTx[_tx_id][leader] = false;
		// 2) another validator is added
		(address[] memory replacements, ) = genStaking.getValidatorsForTx(
			_randomSeed,
			1,
			genTransactions.getConsumedValidators(_tx_id) // avoid re-consuming the same validators
		);
		address replacement = replacements[0];
		validatorsForTx[_tx_id][txLeaderIndex[_tx_id]] = replacement;
		validatorIsActiveForTx[_tx_id][replacement] = true;
		// 3) a new leader is randomly selected from the set
		txLeaderIndex[_tx_id] =
			uint256(
				keccak256(
					abi.encodePacked(
						_randomSeed,
						genTransactions.getConsumedValidatorsLen(_tx_id)
					)
				)
			) %
			validatorsForTx[_tx_id].length;
		// Status and event changes
		txStatus[_tx_id] = ITransactions.TransactionStatus.Proposing;
		emit TransactionLeaderRotated(
			_tx_id,
			validatorsForTx[_tx_id][txLeaderIndex[_tx_id]]
		);
	}

	/**
	 * @notice Resets the votes for a transaction
	 * @param _tx_id The unique identifier of the transaction
	 */
	function _resetVotes(bytes32 _tx_id) internal {
		genTransactions.resetVotes(_tx_id);
		for (uint i = 0; i < validatorsForTx[_tx_id].length; i++) {
			voteCommittedForTx[_tx_id][validatorsForTx[_tx_id][i]] = false;
			voteRevealedForTx[_tx_id][validatorsForTx[_tx_id][i]] = false;
		}
		// reset counters
		voteCommittedCountForTx[_tx_id] = 0;
		voteRevealedCountForTx[_tx_id] = 0;
	}

	/**
	 * @notice Stores a ghost contract address
	 * @param _ghost Address of the ghost contract
	 */
	function _storeGhost(address _ghost) internal {
		ghostContracts[_ghost] = true;
	}

	/**
	 * @notice Generates a new transaction
	 * @param _sender Transaction sender address
	 * @param _recipient Recipient GenVM contract address
	 * @param _numOfInitialValidators Number of validators to assign
	 * @param _maxRotations Maximum number of leader rotations allowed
	 * @param _randomSeed Random seed for the transaction
	 * @param _txData Transaction data to be executed
	 */
	function _generateTx(
		address _sender,
		address _recipient,
		uint256 _numOfInitialValidators,
		uint256 _maxRotations,
		bytes32 _randomSeed,
		bytes memory _txData
	) internal returns (bytes32 tx_id, address activator) {
		tx_id = keccak256(
			abi.encodePacked(_recipient, block.timestamp, _randomSeed)
		);
		(uint256 txSlot, ) = genQueue.addTransactionToPendingQueue(
			_recipient,
			tx_id
		);
		activator = _getActivatorForTx(_randomSeed, txSlot);
		genTransactions.addNewTransaction(
			tx_id,
			ITransactions.Transaction({
				sender: _sender,
				recipient: _recipient,
				numOfInitialValidators: _numOfInitialValidators,
				txSlot: txSlot,
				timestamp: block.timestamp,
				lastModification: block.timestamp,
				lastVoteTimestamp: 0,
				activationTimestamp: 0,
				randomSeed: _randomSeed,
				onAcceptanceMessages: false,
				result: ITransactions.ResultType(0),
				txData: _txData,
				txReceipt: new bytes(0),
				messages: new IMessages.SubmittedMessage[](0),
				validators: new address[](0),
				validatorVotesHash: new bytes32[](0),
				validatorVotes: new ITransactions.VoteType[](0),
				consumedValidators: new address[](0),
				rotationsLeft: _maxRotations
			})
		);
	}

	/**
	 * @notice Activates a pending transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @param _activationInfo Activation information for the transaction
	 * @param _randomSeed Random seed for the transaction
	 */
	function _activateTransaction(
		bytes32 _tx_id,
		ITransactions.ActivationInfo memory _activationInfo,
		bytes32 _randomSeed
	) internal {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Pending) {
			revert Errors.TransactionNotPending();
		}
		if (
			!genQueue.isAtPendingQueueHead(
				_activationInfo.recepientAddress,
				_tx_id
			)
		) {
			revert Errors.TransactionNotAtPendingQueueHead();
		}
		txStatus[_tx_id] = ITransactions.TransactionStatus.Proposing;
		address[] memory consumedValidators;
		if (_activationInfo.initialActivation) {
			consumedValidators = validatorsForTx[_tx_id];
		}
		(
			address[] memory validators,
			uint leaderIndex
		) = _getValidatorsAndLeaderIndex(
				_randomSeed,
				_activationInfo.numOfInitialValidators,
				consumedValidators
			);
		txLeaderIndex[_tx_id] = leaderIndex;
		validatorsForTx[_tx_id] = _activationInfo.initialActivation
			? validators
			: _concatArrays(consumedValidators, validators);
		for (uint i = 0; i < validators.length; i++) {
			validatorIsActiveForTx[_tx_id][validators[i]] = true;
		}
		genTransactions.setActivationData(_tx_id, _randomSeed);
		emit TransactionActivated(_tx_id, validators[leaderIndex], validators);
	}

	/**
	 * @notice Checks if two results are the same
	 * @param _originalResult Original result type
	 * @param _appealResult Appeal result type
	 * @return True if the results are the same, false otherwise
	 */
	function _sameResult(
		ITransactions.ResultType _originalResult,
		ITransactions.ResultType _appealResult
	) internal pure returns (bool) {
		uint8 originalResult = uint8(_originalResult);
		uint8 appealResult = uint8(_appealResult);
		if (originalResult == appealResult) {
			return true;
		} else if (
			originalResult > 5 &&
			appealResult < 5 &&
			originalResult - 5 == appealResult
		) {
			return true;
		} else if (
			originalResult < 5 &&
			appealResult > 5 &&
			appealResult - 5 == originalResult
		) {
			return true;
		}
		return false;
	}

	/**
	 * @notice Retrieves the activator for a transaction
	 * @param _randomSeed Random seed for the transaction
	 * @param _randomIndex Random index for the transaction
	 * @return validator - the address of the validator that will activate the transaction
	 */
	function _getActivatorForTx(
		bytes32 _randomSeed,
		uint256 _randomIndex
	) internal view returns (address validator) {
		bytes32 combinedSeed = keccak256(
			abi.encodePacked(_randomSeed, _randomIndex)
		);
		validator = genStaking.getActivatorForSeed(combinedSeed);
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

	/**
	 * @notice Concatenates two arrays of addresses
	 * @param _array1 First array of addresses
	 * @param _array2 Second array of addresses
	 * @return The concatenated array of addresses
	 */
	function _concatArrays(
		address[] memory _array1,
		address[] memory _array2
	) internal pure returns (address[] memory) {
		address[] memory result = new address[](
			_array1.length + _array2.length
		);
		for (uint i = 0; i < _array1.length; i++) {
			result[i] = _array1[i];
		}
		for (uint i = 0; i < _array2.length; i++) {
			result[_array1.length + i] = _array2[i];
		}
		return result;
	}

	/**
	 * @notice Processes messages for a transaction
	 * @param _tx_id The unique identifier of the transaction
	 * @param isAcceptance Whether the messages are for acceptance or finalization
	 */
	function _processMessages(bytes32 _tx_id, bool isAcceptance) internal {
		IMessages.SubmittedMessage[] memory messages = genTransactions
			.getMessagesForTransaction(_tx_id);

		for (uint i = 0; i < messages.length; i++) {
			IMessages.SubmittedMessage memory message = messages[i];

			// Only process messages for the current phase (acceptance or finalization)
			if (message.onAcceptance != isAcceptance) {
				continue;
			}
			if (message.messageType == IMessages.MessageType.External) {
				// Existing external message handling
				genMessages.executeMessage(message);
			} else if (message.messageType == IMessages.MessageType.Internal) {
				// Get transaction sender (the ghost contract that issued the original transaction)
				ITransactions.ActivationInfo
					memory activationInfo = genTransactions
						.getTransactionActivationInfo(_tx_id);

				// Create new transaction from current ghost to target ghost
				(
					bytes32 generated_tx_id,
					address newActivator
				) = _addTransaction(
						activationInfo.recepientAddress, // sender (current ghost)
						message.recipient, // recipient (target ghost)
						5, // or pass as part of message.data
						0, // or pass as part of message.data
						message.data // transaction data
					);
				emit InternalMessageProcessed(
					generated_tx_id,
					message.recipient,
					newActivator
				);
			}
		}
	}

	// SETTERS

	/**
	 * @notice Sets the ghost factory contract address
	 * @param _ghostFactory Address of the ghost factory contract
	 */
	function setGhostFactory(address _ghostFactory) external onlyOwner {
		ghostFactory = IGhostFactory(_ghostFactory);
		emit GhostFactorySet(_ghostFactory);
	}

	function setGenManager(address _genManager) external onlyOwner {
		genManager = IGenManager(_genManager);
		emit GenManagerSet(_genManager);
	}

	function setGenTransactions(address _genTransactions) external onlyOwner {
		genTransactions = ITransactions(_genTransactions);
		emit GenTransactionsSet(_genTransactions);
	}

	function setGenQueue(address _genQueue) external onlyOwner {
		genQueue = IQueues(_genQueue);
		emit GenQueueSet(_genQueue);
	}

	function setGenStaking(address _genStaking) external onlyOwner {
		genStaking = IGenStaking(_genStaking);
		emit GenStakingSet(_genStaking);
	}

	function setGenMessages(address _genMessages) external onlyOwner {
		genMessages = IMessages(_genMessages);
		emit GenMessagesSet(_genMessages);
	}

	function setGenAppeals(address _genAppeals) external onlyOwner {
		genAppeals = IAppeals(_genAppeals);
		emit GenAppealsSet(_genAppeals);
	}

	function setAcceptanceTimeout(
		uint256 _acceptanceTimeout
	) external onlyOwner {
		ACCEPTANCE_TIMEOUT = _acceptanceTimeout;
	}

	function setActivationTimeout(
		uint256 _activationTimeout
	) external onlyOwner {
		ACTIVATION_TIMEOUT = _activationTimeout;
	}

	// MODIFIERS
	modifier onlyActivator(bytes32 _tx_id) {
		if (txActivator[_tx_id] != msg.sender) {
			revert Errors.CallerNotActivator();
		}
		_;
	}

	modifier onlyLeader(bytes32 _tx_id) {
		if (validatorsForTx[_tx_id][txLeaderIndex[_tx_id]] != msg.sender) {
			revert Errors.CallerNotLeader();
		}
		_;
	}

	modifier onlyValidator(bytes32 _tx_id) {
		if (
			!validatorIsActiveForTx[_tx_id][msg.sender] &&
			!genAppeals.isAppealValidator(_tx_id, msg.sender)
		) {
			revert Errors.CallerNotValidator();
		}
		_;
	}

	// EVENTS
	event GhostFactorySet(address indexed ghostFactory);
	event GenManagerSet(address indexed genManager);
	event GenTransactionsSet(address indexed genTransactions);
	event GenQueueSet(address indexed genQueue);
	event GenStakingSet(address indexed genStaking);
	event GenMessagesSet(address indexed genMessages);
	event GenAppealsSet(address indexed genAppeals);
	event NewTransaction(
		bytes32 indexed tx_id,
		address indexed recipient,
		address indexed activator
	);
	event TransactionLeaderRotated(
		bytes32 indexed tx_id,
		address indexed newLeader
	);
	event TransactionActivated(
		bytes32 indexed tx_id,
		address indexed leader,
		address[] validators
	);
	event TransactionReceiptProposed(bytes32 indexed tx_id);
	event VoteCommitted(
		bytes32 indexed tx_id,
		address indexed validator,
		bool isLastVote
	);
	event VoteRevealed(
		bytes32 indexed tx_id,
		address indexed validator,
		ITransactions.VoteType voteType,
		bool isLastVote,
		ITransactions.ResultType result
	);
	event TransactionAccepted(bytes32 indexed tx_id);
	event TransactionFinalized(bytes32 indexed tx_id);
	event TransactionNeedsRecomputation(bytes32[] tx_ids);
	event AppealStarted(
		bytes32 indexed tx_id,
		address indexed appealer,
		uint256 appealBond,
		uint256 appealIndex
	);
	event InternalMessageProcessed(
		bytes32 indexed tx_id,
		address indexed recipient,
		address indexed activator
	);
	event TransactionCancelled(bytes32 indexed tx_id, address indexed sender);
}