// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGenManager {
	function updateRandomSeedForRecipient(
		address _recipient,
		address _sender,
		bytes calldata _vrfProof
	) external returns (bytes32 randomSeed);

	function addNewRandomSeedForRecipient(
		address _recipient,
		bytes32 _randomSeed
	) external;

	function recipientRandomSeed(
		address _recipient
	) external view returns (bytes32);
}