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
import "../RandomnessUtils.sol";
import "./utils/Errors.sol";

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
	mapping(bytes32 => ITransactions.TransactionStatus) public txStatus;
	mapping(address => bool) public ghostContracts;
	mapping(bytes32 => address) public txActivator;
	mapping(bytes32 => uint) public txLeaderIndex;
	mapping(bytes32 => address[]) public validatorsForTx;
	mapping(bytes32 => uint) public validatorsCountForTx;
	mapping(bytes32 => mapping(address => bool)) public validatorIsActiveForTx;
	mapping(bytes32 => mapping(address => bool)) public voteCommittedForTx;
	mapping(bytes32 => uint) public voteCommittedCountForTx;
	mapping(bytes32 => mapping(address => bool)) public voteRevealedForTx;
	mapping(bytes32 => uint) public voteRevealedCountForTx;
	mapping(address => bytes32) public recipientRandomSeed;
	mapping(address => uint256) public recipientRandomParallelIndex; // for many addTransaction() in a row

	event GhostFactorySet(address indexed ghostFactory);
	event GenManagerSet(address indexed genManager);
	event GenTransactionsSet(address indexed genTransactions);
	event GenQueueSet(address indexed genQueue);
	event GenStakingSet(address indexed genStaking);
	event GenMessagesSet(address indexed genMessages);
	event NewTransaction(
		bytes32 indexed tx_id,
		address indexed recipient,
		address indexed activator
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
	receive() external payable {}

	function initialize(address _genManager) public initializer {
		__Ownable2Step_init();
		__Ownable_init(msg.sender);
		__ReentrancyGuard_init();
		__AccessControl_init();
		genManager = IGenManager(_genManager);
	}

	// EXTERNAL FUNCTIONS

	function getValidatorsForTx(
		bytes32 _tx_id
	) external view returns (address[] memory) {
		return validatorsForTx[_tx_id];
	}

	function addTransaction(
		address _sender,
		address _recipient, // _recipient GenVM contract address, can be a EOA or a GenVM contract
		uint256 _numOfInitialValidators,
		bytes memory _txData
	) external {
		if (_sender == address(0)) {
			_sender = msg.sender;
		}
		if (_recipient == address(0)) {
			// Contract deployment transaction
			ghostFactory.createGhost();
			address ghost = ghostFactory.latestGhost();
			_storeGhost(ghost);
			_recipient = ghost;
			// Initial random seed for the recipient account
			recipientRandomSeed[_recipient] = keccak256(
				abi.encodePacked(ghost)
			);
			recipientRandomParallelIndex[_recipient] = 1;
		} else if (!ghostContracts[_recipient]) {
			revert Errors.NonGenVMContract();
		}
		bytes32 randomSeed = recipientRandomSeed[_recipient]; // recipient randomSeed is used for activation
		uint256 randomIndex = recipientRandomParallelIndex[_recipient]++; // for many addTransaction() in a row
		bytes32 tx_id = _generateTx(
			_sender,
			_recipient,
			_numOfInitialValidators,
			bytes32(0), // tx randomSeed is set later
			_txData
		);
		address activator = _getActivatorForTx(
			randomSeed,
			randomIndex,
			block.timestamp
		); // unweighted validator for activation
		txActivator[tx_id] = activator;
		txStatus[tx_id] = ITransactions.TransactionStatus.Pending;
		emit NewTransaction(tx_id, _recipient, activator);
		// TODO: Fee verification handling
	}

	function activateTransaction(
		bytes32 _tx_id,
		bytes calldata _vrfProof
	) external onlyActivator(_tx_id) {
		require(
			txStatus[_tx_id] == ITransactions.TransactionStatus.Pending,
			"Transaction is not pending"
		);
		txStatus[_tx_id] = ITransactions.TransactionStatus.Proposing;
		// genQueue.activateTransaction(_tx_id);
		// TODO: change to storage to update randomSeed
		ITransactions.Transaction memory _tx = genTransactions.getTransaction(
			_tx_id
		);
		bytes32 randomSeed = recipientRandomSeed[_tx.recipient];
		// TODO: Possibly not needed to allow for parallel activations
		// require(
		// 	genQueue.isAtPendingQueueHead(_tx.recipient, _tx_id),
		// 	"Transaction is not at the pending queue head"
		// );
		randomSeed = bytes32(
			RandomnessUtils.updateRandomSeed(
				_vrfProof,
				uint256(randomSeed),
				msg.sender
			)
		);
		// update recipient randomSeed
		recipientRandomSeed[_tx.recipient] = randomSeed;
		recipientRandomParallelIndex[_tx.recipient] = 1; //  reset
		// initialize tx randomSeed
		genTransactions.setRandomSeed(_tx_id, randomSeed);
		genTransactions.setActivationTimestamp(_tx_id, block.timestamp);
		(
			address[] memory validators,
			uint leaderIndex
		) = _getValidatorsAndLeaderIndex(
				_tx_id,
				randomSeed,
				block.timestamp,
				_tx.numOfInitialValidators,
				_tx.consumedValidators
			);
		txLeaderIndex[_tx_id] = leaderIndex;
		validatorsForTx[_tx_id] = validators;
		validatorsCountForTx[_tx_id] = validators.length;
		for (uint i = 0; i < validators.length; i++) {
			validatorIsActiveForTx[_tx_id][validators[i]] = true;
		}
		emit TransactionActivated(_tx_id, validators[leaderIndex], validators);
	}

	function proposeReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		IMessages.SubmittedMessage[] calldata _messages,
		bytes calldata _vrfProof
	) external onlyLeader(_tx_id) {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Proposing) {
			revert Errors.TransactionNotProposing();
		}
		ITransactions.Transaction memory _tx = genTransactions.getTransaction(
			_tx_id
		);
		// TODO: Possibly *needed* to avoid for parallel receipts
		require(
			genQueue.isAtPendingQueueHead(_tx.recipient, _tx_id),
			"Transaction is not at the pending queue head"
		);
		bytes32 randomSeed = recipientRandomSeed[_tx.recipient];
		randomSeed = bytes32(
			RandomnessUtils.updateRandomSeed(
				_vrfProof,
				uint256(randomSeed),
				msg.sender
			)
		);
		// update recipient randomSeed
		recipientRandomSeed[_tx.recipient] = randomSeed;
		recipientRandomParallelIndex[_tx.recipient] = 1; //  reset

		txStatus[_tx_id] = ITransactions.TransactionStatus.Committing;
		genTransactions.proposeTransactionReceipt(
			_tx_id,
			_txReceipt,
			_messages
		);

		emit TransactionReceiptProposed(_tx_id);
	}

	function commitVote(
		bytes32 _tx_id,
		bytes32 _commitHash,
		bool _isAppeal
	) external onlyValidator(_tx_id) {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Committing) {
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

	function revealVote(
		bytes32 _tx_id,
		bytes32 _voteHash,
		ITransactions.VoteType _voteType,
		uint _nonce
	) external onlyValidator(_tx_id) {
		ITransactions.Transaction memory _tx = genTransactions.getTransaction(
			_tx_id
		);
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
				result == ITransactions.ResultType.MajorityDisagree ||
				result == ITransactions.ResultType.DeterministicViolation ||
				result == ITransactions.ResultType.NoMajority
			) {
				txStatus[_tx_id] = ITransactions.TransactionStatus.Undetermined;
				genQueue.addTransactionToUndeterminedQueue(
					_tx.recipient,
					_tx_id
				);
			} else {
				txStatus[_tx_id] = ITransactions.TransactionStatus.Accepted;
				genQueue.addTransactionToAcceptedQueue(_tx.recipient, _tx_id);
				emit TransactionAccepted(_tx_id);
				if (genTransactions.hasOnAcceptanceMessages(_tx_id)) {
					genMessages.emitMessagesOnAcceptance(_tx_id);
				}
			}
		}
		emit VoteRevealed(_tx_id, msg.sender, _voteType, isLastVote, result);
	}

	function finalizeTransaction(bytes32 _tx_id) external {
		if (
			txStatus[_tx_id] != ITransactions.TransactionStatus.Accepted &&
			txStatus[_tx_id] != ITransactions.TransactionStatus.Undetermined
		) {
			revert Errors.TransactionNotAcceptedOrUndetermined();
		}
		uint lastVoteTimestamp = genTransactions
			.getTransactionLastVoteTimestamp(_tx_id);
		if (block.timestamp - lastVoteTimestamp > ACCEPTANCE_TIMEOUT) {
			txStatus[_tx_id] = ITransactions.TransactionStatus.Finalized;
			// TODO: Emit the messages
			if (genTransactions.hasMessagesOnFinalization(_tx_id)) {
				genMessages.emitMessagesOnFinalization(_tx_id);
			}
			emit TransactionFinalized(_tx_id);
		}
	}

	function submitAppeal(bytes32 _tx_id) external payable {
		if (
			txStatus[_tx_id] != ITransactions.TransactionStatus.Undetermined &&
			txStatus[_tx_id] != ITransactions.TransactionStatus.Accepted
		) {
			revert Errors.CanNotAppeal();
		}
		uint minBond = genTransactions.getMinAppealBond(_tx_id);
		if (msg.value < minBond) {
			revert Errors.AppealBondTooLow();
		}
		txStatus[_tx_id] = ITransactions.TransactionStatus.Appealed;
		// Select validators for appeal
		// Update the number of validators in the appeal
		// Start appeal voting
	}

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

	// INTERNAL FUNCTIONS
	function _storeGhost(address _ghost) internal {
		ghostContracts[_ghost] = true;
	}

	function _generateTx(
		address _sender,
		address _recipient,
		uint256 _numOfInitialValidators,
		bytes32 _randomSeed,
		bytes memory _txData
	) internal returns (bytes32 tx_id) {
		tx_id = keccak256(
			abi.encodePacked(_recipient, block.timestamp, _randomSeed)
		);
		uint256 txSlot = genQueue.addTransactionToPendingQueue(
			_recipient,
			tx_id
		);
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
				consumedValidators: new address[](0)
			})
		);
	}

	function _getActivatorForTx(
		bytes32 _randomSeed,
		uint256 _randomIndex,
		uint256 timestamp
	) internal view returns (address validator) {
		// TODO: Get a single validator from the list of validators based on the random seed
		bytes32 combinedSeed = keccak256(
			abi.encodePacked(_randomSeed, _randomIndex)
		);
		validator = genStaking.getActivatorForSeed(combinedSeed, timestamp);
	}

	function _getValidatorsAndLeaderIndex(
		bytes32 _tx_id,
		bytes32 _randomSeed,
		uint256 timestamp,
		uint256 numValidators,
		address[] memory consumedValidators
	) internal returns (address[] memory validators, uint256 leaderIndex) {
		validators = genStaking.getValidatorsForTx(
			_tx_id,
			_randomSeed,
			timestamp,
			numValidators,
			consumedValidators
		);
		// TODO: Get the leader index from random number generator
		leaderIndex = 0;
	}

	// SETTERS
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
		if (!validatorIsActiveForTx[_tx_id][msg.sender]) {
			revert Errors.CallerNotValidator();
		}
		_;
	}
}