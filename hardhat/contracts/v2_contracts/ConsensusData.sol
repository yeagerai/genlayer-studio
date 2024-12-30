// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IQueues.sol";
import "./interfaces/IConsensusMain.sol";
import "./interfaces/IMessages.sol";

contract ConsensusData is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	ITransactions public transactions;
	IQueues public queues;
	IConsensusMain public consensusMain;
	struct TransactionData {
		// Basic transaction info
		address sender;
		address recipient;
		uint256 numOfInitialValidators;
		uint256 txSlot;
		uint256 timestamp;
		uint256 lastVoteTimestamp;
		bytes32 randomSeed;
		ITransactions.ResultType result;
		bytes txData;
		bytes txReceipt;
		IMessages.SubmittedMessage[] messages;
		// // Validator info
		address[] validators;
		bytes32[] validatorVotesHash;
		ITransactions.VoteType[] validatorVotes;
		// Queue info
		IQueues.QueueType queueType;
		uint256 queuePosition;
		// // Status info
		address activator;
		address leader;
		ITransactions.TransactionStatus status;
		uint256 committedVotesCount;
		uint256 revealedVotesCount;
	}

	receive() external payable {}

	function initialize(
		address _consensusMain,
		address _transactions,
		address _queues
	) public initializer {
		__Ownable2Step_init();
		__ReentrancyGuard_init();
		__AccessControl_init();

		transactions = ITransactions(_transactions);
		queues = IQueues(_queues);
		consensusMain = IConsensusMain(_consensusMain);
	}

	function getTransactionData(
		bytes32 _tx_id
	) external view returns (TransactionData memory) {
		ITransactions.Transaction memory transaction = transactions
			.getTransaction(_tx_id);

		address activator = consensusMain.txActivator(_tx_id);
		uint validatorsCount = consensusMain.validatorsCountForTx(_tx_id);
		address[] memory validators = consensusMain.getValidatorsForTx(_tx_id);
		uint leaderIndex = consensusMain.txLeaderIndex(_tx_id);
		address leader = validatorsCount > 0
			? validators[leaderIndex]
			: address(0);

		TransactionData memory txData = TransactionData({
			// Basic transaction info
			sender: transaction.sender,
			recipient: transaction.recipient,
			numOfInitialValidators: transaction.numOfInitialValidators,
			txSlot: transaction.txSlot,
			timestamp: transaction.timestamp,
			lastVoteTimestamp: transaction.lastVoteTimestamp,
			randomSeed: transaction.randomSeed,
			result: transaction.result,
			txData: transaction.txData,
			txReceipt: transaction.txReceipt,
			messages: transaction.messages,
			// // Validator info
			validators: transaction.validators,
			validatorVotesHash: transaction.validatorVotesHash,
			validatorVotes: transaction.validatorVotes,
			// Queue info
			queueType: queues.getTransactionQueueType(_tx_id),
			queuePosition: queues.getTransactionQueuePosition(_tx_id),
			// // Status info
			activator: activator,
			leader: leader,
			status: consensusMain.txStatus(_tx_id),
			committedVotesCount: consensusMain.voteCommittedCountForTx(_tx_id),
			revealedVotesCount: consensusMain.voteRevealedCountForTx(_tx_id)
		});

		return txData;
	}

	// Setter functions
	function setTransactions(address _transactions) external onlyOwner {
		transactions = ITransactions(_transactions);
	}

	function setQueues(address _queues) external onlyOwner {
		queues = IQueues(_queues);
	}

	function setConsensusMain(address _consensusMain) external onlyOwner {
		consensusMain = IConsensusMain(_consensusMain);
	}
}