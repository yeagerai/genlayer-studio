// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";

contract Queues is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	enum QueueType {
		Pending,
		Accepted,
		Undetermined
	}

	error NotConsensus();

	address public genConsensus;
	mapping(address => mapping(bytes32 => uint)) public recipientToTxIdToSlot;
	mapping(address => mapping(bytes32 => QueueType))
		public recipientToTxIdToQueueType;
	mapping(address => uint) public recipientToPendingQueueHead;
	mapping(address => uint) public recipientToPendingQueueTail;
	mapping(address => uint) public recipientToAcceptedQueueHead;
	mapping(address => uint) public recipientToAcceptedQueueTail;
	mapping(address => uint) public recipientToUndeterminedQueueHead;
	mapping(address => uint) public recipientToUndeterminedQueueTail;

	function initialize(address _genConsensus) public initializer {
		__Ownable_init(msg.sender);
		__Ownable2Step_init();
		__ReentrancyGuard_init();
		__AccessControl_init();
		genConsensus = _genConsensus;
	}

	function addTransactionToPendingQueue(
		address recipient,
		bytes32 txId
	) external onlyConsensus returns (uint slot) {
		recipientToTxIdToQueueType[recipient][txId] = QueueType.Pending;
		slot = recipientToPendingQueueTail[recipient];
		recipientToTxIdToSlot[recipient][txId] = slot;
		recipientToPendingQueueTail[recipient]++;
	}

	function addTransactionToAcceptedQueue(
		address recipient,
		bytes32 txId
	) external onlyConsensus returns (uint slot) {
		// Remove from pending queue by setting slot to max uint
		recipientToTxIdToQueueType[recipient][txId] = QueueType.Accepted;
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
		recipientToTxIdToQueueType[recipient][txId] = QueueType.Undetermined;
		recipientToPendingQueueHead[recipient]++;
		slot = recipientToUndeterminedQueueTail[recipient];
		recipientToTxIdToSlot[recipient][txId] = slot;
		recipientToUndeterminedQueueTail[recipient]++;
	}

	modifier onlyConsensus() {
		if (msg.sender != genConsensus) {
			revert NotConsensus();
		}
		_;
	}
}
