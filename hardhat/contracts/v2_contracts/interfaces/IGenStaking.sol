// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGenStaking {
	/**
	 * @notice Gets the validator that should activate a transaction for a specific recipient
	 * @param _recipient The address of the contract receiving the transaction
	 * @param _randomSeed A random seed used to select the validator
	 * @return validator The address of the selected validator
	 */
	function getActivatorForTx(
		address _recipient,
		bytes32 _randomSeed
	) external view returns (address validator);

	/**
	 * @notice Gets the validators that should participate in a transaction
	 * @param _tx_id The id of the transaction
	 * @param _randomSeed A random seed used to select the validators
	 * @return validators The addresses of the selected validators
	 */
	function getValidatorsForTx(
		bytes32 _tx_id,
		bytes32 _randomSeed
	) external view returns (address[] memory validators);
}
