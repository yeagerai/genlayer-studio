// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "./ITransactions.sol";

interface IConsensusMain {
	struct addTransactionParams {
		address sender;
		bytes data;
	}

	function txStatus(
		bytes32 _tx_id
	) external view returns (ITransactions.TransactionStatus);

	function txActivator(bytes32 _tx_id) external view returns (address);

	function txLeaderIndex(bytes32 _tx_id) external view returns (uint);

	function validatorsCountForTx(bytes32 _tx_id) external view returns (uint);

	function getValidatorsForTx(
		bytes32 _tx_id
	) external view returns (address[] memory);

	function voteCommittedCountForTx(
		bytes32 _tx_id
	) external view returns (uint);

	function voteRevealedCountForTx(
		bytes32 _tx_id
	) external view returns (uint);

	function validatorIsActiveForTx(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool);

	function voteCommittedForTx(
		bytes32 _tx_id,
		address _validator
	) external view returns (bool);

	function addTransaction(bytes memory _transaction) external;

	function isCurrentActivator(
		uint256 lastModification,
		uint256 addedTimestamp,
		bytes32 randomSeed
	) external view returns (bool);

	function activateTransaction(
		bytes32 _tx_id,
		bytes calldata _vrfProof
	) external;

	function proposeReceipt(
		bytes memory _receipt,
		bytes calldata _vrfProof
	) external;

	function commitVote(bytes32 _tx_id, bytes32 _voteHash) external;

	function revealVote(bytes32 _tx_id, bytes32 _voteHash) external;

	function finalizeTransaction(bytes32 _tx_id) external;
}