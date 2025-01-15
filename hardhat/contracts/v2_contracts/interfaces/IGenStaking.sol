// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGenStaking {
	/**
	 * @notice Gets the validator that should activate a transaction for a specific recipient
	 * @param _randomSeed A random seed used to select the validator
	 * @param timestamp The added timestemp of the transaction
	 * @return validator The address of the selected validator
	 */
	function getActivatorForSeed(
		bytes32 _randomSeed,
		uint256 timestamp
	) external view returns (address validator);

	/**
	 * @notice Gets the validators that should participate in a transaction
	 * @param _tx_id The id of the transaction
	 * @param _randomSeed A random seed used to select the validators
	 * @param timestamp The added timestemp of the transaction
	 * @param numValidators The number of validators to select
	 * @return validators The addresses of the selected validators
	 * @param consumedValidators The addresses of the validators that have already participated in the transaction
	 */
	function getValidatorsForTx(
		bytes32 _tx_id,
		bytes32 _randomSeed,
		uint256 timestamp,
		uint256 numValidators,
		address[] memory consumedValidators
	) external view returns (address[] memory validators);

	/**
	 * @notice Gets the length of the validators that should participate in a transaction
	 * @param timestamp The added timestemp of the transaction
	 */
	function getValidatorsLen(
		uint256 timestamp
	) external view returns (uint256);

	/**
	 * @notice Gets the validator at a specific index
	 * @param index The index of the validator
	 * @param timestamp The added timestemp of the transaction
	 */
	function getValidatorsItem(
		uint256 index,
		uint256 timestamp
	) external view returns (address);
}