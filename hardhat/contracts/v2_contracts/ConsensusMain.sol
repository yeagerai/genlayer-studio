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

contract ConsensusMain is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	error NonGenVMContract();
	error TransactionNotProposing();
	error CallerNotActivator();
	error CallerNotLeader();
	error CallerNotValidator();
	error TransactionNotCommitting();
	error VoteAlreadyCommitted();
	error TransactionNotRevealing();
	error VoteAlreadyRevealed();
	error InvalidVote();
	error TransactionNotAcceptedOrUndetermined();

	bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
	bytes32 public constant VALIDATOR_ROLE = keccak256("VALIDATOR_ROLE");

	uint256 public ACCEPTANCE_TIMEOUT;

	IGenManager public genManager;
	ITransactions public genTransactions;
	IQueues public genQueue;
	IGhostFactory public ghostFactory;
	IGenStaking public genStaking;

	mapping(bytes32 => ITransactions.TransactionStatus) public txStatus;
	mapping(address => bool) public ghostContracts;
	mapping(bytes32 => address) public txActivator;
	mapping(bytes32 => uint) public txLeaderIndex;
	mapping(bytes32 => address[]) public validatorsForTx;
	mapping(bytes32 => mapping(address => bool)) public validatorIsActiveForTx;
	mapping(bytes32 => mapping(address => bool)) public voteCommittedForTx;
	mapping(bytes32 => uint) public voteCommittedCountForTx;
	mapping(bytes32 => mapping(address => bool)) public voteRevealedForTx;

	event GhostFactorySet(address indexed ghostFactory);
	event GenManagerSet(address indexed genManager);
	event GenTransactionsSet(address indexed genTransactions);
	event GenQueueSet(address indexed genQueue);
	event GenStakingSet(address indexed genStaking);
	event NewTransaction(
		bytes32 indexed tx_id,
		address indexed recipient,
		address indexed activator
	);
	event TransactionActivated(bytes32 indexed tx_id, address indexed leader);
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
			address ghost = ghostFactory.createGhost();
			_storeGhost(ghost);
			_recipient = ghost;
		} else if (!ghostContracts[_recipient]) {
			revert NonGenVMContract();
		}
		// TODO: Jose Ignacio: change to VRF
		bytes32 randomSeed = keccak256(
			abi.encodePacked((block.timestamp / 20) % 1000)
		); // TODO: Change to VRF
		bytes32 tx_id = _generateTx(
			_sender,
			_recipient,
			_numOfInitialValidators,
			randomSeed,
			_txData
		);
		address activator = _getActivatorForTx(_recipient, randomSeed);
		txActivator[tx_id] = activator;
		txStatus[tx_id] = ITransactions.TransactionStatus.Pending;
		emit NewTransaction(tx_id, _recipient, activator);
		// TODO: Fee verification handling
	}

	function activateTransaction(
		bytes32 _tx_id
	) external onlyActivator(_tx_id) {
		require(
			txStatus[_tx_id] == ITransactions.TransactionStatus.Pending,
			"Transaction is not pending"
		);
		txStatus[_tx_id] = ITransactions.TransactionStatus.Proposing;
		// genQueue.activateTransaction(_tx_id);
		bytes32 randomSeed = genTransactions.getTransactionSeed(_tx_id);
		(
			address[] memory validators,
			uint leaderIndex
		) = _getValidatorsAndLeaderIndex(_tx_id, randomSeed);
		txLeaderIndex[_tx_id] = leaderIndex;
		validatorsForTx[_tx_id] = validators;
		for (uint i = 0; i < validators.length; i++) {
			validatorIsActiveForTx[_tx_id][validators[i]] = true;
		}
		emit TransactionActivated(_tx_id, validators[leaderIndex]);
	}

	function proposeReceipt(
		bytes32 _tx_id,
		bytes calldata _txReceipt,
		bytes[] calldata _messages
	) external onlyLeader(_tx_id) {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Proposing) {
			revert TransactionNotProposing();
		}
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
		bytes32 _commitHash
	) external onlyValidator(_tx_id) {
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Committing) {
			revert TransactionNotCommitting();
		}
		if (voteCommittedForTx[_tx_id][msg.sender]) {
			revert VoteAlreadyCommitted();
		}
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
		if (txStatus[_tx_id] != ITransactions.TransactionStatus.Revealing) {
			revert TransactionNotRevealing();
		}
		if (voteRevealedForTx[_tx_id][msg.sender]) {
			revert VoteAlreadyRevealed();
		}
		if (
			keccak256(abi.encodePacked(msg.sender, _voteType, _nonce)) !=
			_voteHash
		) {
			revert InvalidVote();
		}
		(bool isLastVote, ITransactions.ResultType result) = genTransactions
			.revealVote(_tx_id, _voteHash, _voteType, msg.sender);
		if (isLastVote) {
			if (
				result == ITransactions.ResultType.MajorityDisagree ||
				result == ITransactions.ResultType.DeterministicViolation ||
				result == ITransactions.ResultType.NoMajority
			) {
				txStatus[_tx_id] = ITransactions.TransactionStatus.Undetermined;
			} else {
				txStatus[_tx_id] = ITransactions.TransactionStatus.Accepted;
				emit TransactionAccepted(_tx_id);
			}
		}
		emit VoteRevealed(_tx_id, msg.sender, _voteType, isLastVote, result);
	}

	function finalizeTransaction(bytes32 _tx_id) external {
		if (
			txStatus[_tx_id] != ITransactions.TransactionStatus.Accepted &&
			txStatus[_tx_id] != ITransactions.TransactionStatus.Undetermined
		) {
			revert TransactionNotAcceptedOrUndetermined();
		}
		uint lastVoteTimestamp = genTransactions
			.getTransactionLastVoteTimestamp(_tx_id);
		if (block.timestamp - lastVoteTimestamp > ACCEPTANCE_TIMEOUT) {
			txStatus[_tx_id] = ITransactions.TransactionStatus.Finalized;
			// TODO: Emit the messages
			emit TransactionFinalized(_tx_id);
			genTransactions.emitMessagesOnFinalization(_tx_id);
		}
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
				lastVoteTimestamp: 0,
				randomSeed: _randomSeed,
				result: ITransactions.ResultType(0),
				txData: _txData,
				txReceipt: new bytes(0),
				messages: new bytes[](0),
				validators: new address[](0),
				validatorVotesHash: new bytes32[](0),
				validatorVotes: new ITransactions.VoteType[](0)
			})
		);
	}

	function _getActivatorForTx(
		address _recipient,
		bytes32 _randomSeed
	) internal view returns (address validator) {
		// TODO: Get a single validator from the list of validators based on the random seed
		validator = genStaking.getActivatorForTx(_recipient, _randomSeed);
	}

	function _getValidatorsAndLeaderIndex(
		bytes32 _tx_id,
		bytes32 _randomSeed
	) internal view returns (address[] memory validators, uint256 leaderIndex) {
		validators = genStaking.getValidatorsForTx(_tx_id, _randomSeed);
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

	function setAcceptanceTimeout(
		uint256 _acceptanceTimeout
	) external onlyOwner {
		ACCEPTANCE_TIMEOUT = _acceptanceTimeout;
	}

	// MODIFIERS
	modifier onlyActivator(bytes32 _tx_id) {
		if (txActivator[_tx_id] != msg.sender) {
			revert CallerNotActivator();
		}
		_;
	}

	modifier onlyLeader(bytes32 _tx_id) {
		if (validatorsForTx[_tx_id][txLeaderIndex[_tx_id]] != msg.sender) {
			revert CallerNotLeader();
		}
		_;
	}

	modifier onlyValidator(bytes32 _tx_id) {
		if (!validatorIsActiveForTx[_tx_id][msg.sender]) {
			revert CallerNotValidator();
		}
		_;
	}
}
