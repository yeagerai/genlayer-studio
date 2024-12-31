// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/IQueues.sol";

contract Queues is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	error NotConsensus();

	address public genConsensus;
	mapping(address => mapping(bytes32 => uint)) public recipientToTxIdToSlot;
	mapping(address => mapping(bytes32 => IQueues.QueueType))
		public recipientToTxIdToQueueType;
	mapping(address => uint) public recipientToPendingQueueHead;
	mapping(address => uint) public recipientToPendingQueueTail;
	mapping(address => uint) public recipientToAcceptedQueueHead;
	mapping(address => uint) public recipientToAcceptedQueueTail;
	mapping(address => uint) public recipientToUndeterminedQueueHead;
	mapping(address => uint) public recipientToUndeterminedQueueTail;

	event GenConsensusSet(address indexed genConsensus);
	function initialize(address _genConsensus) public initializer {
		__Ownable_init(msg.sender);
		__Ownable2Step_init();
		__ReentrancyGuard_init();
		__AccessControl_init();
		genConsensus = _genConsensus;
	}

	function getTransactionQueueType(
		bytes32 txId
	) external view returns (IQueues.QueueType) {
		return recipientToTxIdToQueueType[msg.sender][txId];
	}

	function getTransactionQueuePosition(
		bytes32 txId
	) external view returns (uint) {
		return recipientToTxIdToSlot[msg.sender][txId];
	}

	function addTransactionToPendingQueue(
		address recipient,
		bytes32 txId
	) external onlyConsensus returns (uint slot) {
		recipientToTxIdToQueueType[recipient][txId] = IQueues.QueueType.Pending;
		slot = recipientToPendingQueueTail[recipient];
		recipientToTxIdToSlot[recipient][txId] = slot;
		recipientToPendingQueueTail[recipient]++;
	}

	function addTransactionToAcceptedQueue(
		address recipient,
		bytes32 txId
	) external onlyConsensus returns (uint slot) {
		// Remove from pending queue by setting slot to max uint
		recipientToTxIdToQueueType[recipient][txId] = IQueues
			.QueueType
			.Accepted;
		recipientToPendingQueueHead[recipient]++;
		slot = recipientToAcceptedQueueTail[recipient];
		recipientToTxIdToSlot[recipient][txId] = slot;
		recipientToAcceptedQueueTail[recipient]++;
	}

	function addTransactionToUndeterminedQueue(
		address recipient,
		bytes32 txId
	) external onlyConsensus returns (uint slot) {
		// Remove from pending queue by setting slot to max uint
		recipientToTxIdToQueueType[recipient][txId] = IQueues
			.QueueType
			.Undetermined;
		recipientToPendingQueueHead[recipient]++;
		slot = recipientToUndeterminedQueueTail[recipient];
		recipientToTxIdToSlot[recipient][txId] = slot;
		recipientToUndeterminedQueueTail[recipient]++;
	}

	function setGenConsensus(address _genConsensus) external onlyOwner {
		genConsensus = _genConsensus;
		emit GenConsensusSet(_genConsensus);
	}

	modifier onlyConsensus() {
		if (msg.sender != genConsensus) {
			revert NotConsensus();
		}
		_;
	}

	function isAtPendingQueueHead(
		address recipient,
		bytes32 txId
	) external view returns (bool) {
		uint slot = recipientToTxIdToSlot[recipient][txId];
		return slot == recipientToPendingQueueHead[recipient];
	}

	// function setRecipientRandomSeed(
	// 	address recipient,
	// 	bytes32 randomSeed
	// ) external {
	// 	_setRecipientRandomSeed(recipient, randomSeed);
	// }

	// function _setRecipientRandomSeed(
	// 	address recipient,
	// 	bytes32 randomSeed
	// ) internal {
	// 	recipientRandomSeed[recipient] = randomSeed;
	// }

	// function getRecipientRandomSeed(
	// 	address recipient
	// ) external view returns (bytes32) {
	// 	return _getRecipientRandomSeed(recipient);
	// }

	// function _getRecipientRandomSeed(address recipient)
	// 	internal
	// 	view
	// 	returns (bytes32)
	// {
	// 	return recipientRandomSeed[recipient];
	// }
}