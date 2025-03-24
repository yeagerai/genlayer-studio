// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./interfaces/ITransactions.sol";
import "./interfaces/IQueues.sol";
import "./interfaces/IGenManager.sol";
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
		uint256 rotationsLeft;
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
		bytes32 randomSeed = consensusMain
			.contracts()
			.genManager
			.recipientRandomSeed(transaction.recipient);
		// uint256 txSlot = queues.getTransactionQueuePosition(_tx_id);
		// address activator = consensusMain.getActivatorForTx(randomSeed, txSlot);
		address activator = transaction.activator;
		uint256 txSlot = transaction.txSlot;
		uint lastRound = transaction.roundData.length > 0
			? transaction.roundData.length - 1
			: 0;
		ITransactions.RoundData memory lastRoundData = transaction
			.roundData
			.length > 0
			? transaction.roundData[lastRound]
			: ITransactions.RoundData(
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
			);
		uint validatorsCount = lastRoundData.roundValidators.length;
		uint leaderIndex = lastRoundData.leaderIndex;
		address[] memory validators = lastRoundData.roundValidators;
		address leader = validatorsCount > 0
			? validators[leaderIndex]
			: address(0);
		randomSeed = transaction.randomSeed != bytes32(0)
			? transaction.randomSeed
			: randomSeed;
		TransactionData memory txData = TransactionData({
			// Basic transaction info
			sender: transaction.sender,
			recipient: transaction.recipient,
			numOfInitialValidators: transaction.numOfInitialValidators,
			txSlot: txSlot,
			timestamp: transaction.timestamp,
			lastVoteTimestamp: transaction.lastVoteTimestamp,
			randomSeed: randomSeed,
			result: lastRoundData.result,
			txData: transaction.txData,
			txReceipt: transaction.txReceipt,
			messages: transaction.messages,
			// Validator info
			validators: validators,
			validatorVotesHash: lastRoundData.validatorVotesHash,
			validatorVotes: lastRoundData.validatorVotes,
			// Queue info
			queueType: queues.getTransactionQueueType(_tx_id),
			queuePosition: queues.getTransactionQueuePosition(_tx_id),
			// Status info
			activator: activator,
			leader: leader,
			status: transaction.status,
			committedVotesCount: lastRoundData.votesCommitted,
			revealedVotesCount: lastRoundData.votesRevealed,
			rotationsLeft: lastRoundData.rotationsLeft
		});

		return txData;
	}

	function getValidatorsForLastAppeal(
		bytes32 _tx_id
	) external view returns (address[] memory) {
		ITransactions.Transaction memory transaction = transactions
			.getTransaction(_tx_id);
		uint256 lastRound = transaction.roundData.length > 0
			? transaction.roundData.length - 1
			: 0;
		if (lastRound > 0) {
			if (lastRound % 2 == 1) {
				return transaction.roundData[lastRound].roundValidators;
			} else {
				return transaction.roundData[lastRound - 1].roundValidators;
			}
		} else {
			return new address[](0);
		}
	}

	function getValidatorsForLastRound(
		bytes32 _tx_id
	) external view returns (address[] memory) {
		ITransactions.Transaction memory transaction = transactions
			.getTransaction(_tx_id);
		uint256 lastRound = transaction.roundData.length > 0
			? transaction.roundData.length - 1
			: 0;
		return transaction.roundData[lastRound].roundValidators;
	}

	function getLastAppealResult(
		bytes32 _tx_id
	) external view returns (ITransactions.ResultType) {
		ITransactions.Transaction memory transaction = transactions
			.getTransaction(_tx_id);
		uint256 lastRound = transaction.roundData.length > 0
			? transaction.roundData.length - 1
			: 0;
		if (lastRound > 0) {
			if (lastRound % 2 == 1) {
				return transaction.roundData[lastRound].result;
			} else {
				return transaction.roundData[lastRound - 1].result;
			}
		} else {
			return ITransactions.ResultType(0);
		}
	}

	function getTransactionStatus(
		bytes32 _tx_id
	) external view returns (ITransactions.TransactionStatus) {
		return transactions.getTransaction(_tx_id).status;
	}

	function hasTransactionOnAcceptanceMessages(
		bytes32 _tx_id
	) external view returns (bool) {
		return transactions.getTransaction(_tx_id).onAcceptanceMessages;
	}

	function hasTransactionOnFinalizationMessages(
		bytes32 _tx_id
	) external view returns (bool) {
		return transactions.hasMessagesOnFinalization(_tx_id);
	}

	function getMessagesForTransaction(
		bytes32 _tx_id
	) external view returns (IMessages.SubmittedMessage[] memory) {
		return transactions.getMessagesForTransaction(_tx_id);
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