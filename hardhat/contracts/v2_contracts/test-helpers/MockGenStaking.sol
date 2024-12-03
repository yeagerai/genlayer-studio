// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract MockGenStaking {
	address[] public validators;
	mapping(address => bool) public isValidator;

	constructor(address _initialValidator) {
		_addValidator(_initialValidator);
	}

	function _addValidator(address _validator) private {
		if (!isValidator[_validator]) {
			validators.push(_validator);
			isValidator[_validator] = true;
		}
	}

	function addValidator(address _validator) external {
		_addValidator(_validator);
	}

	function addValidators(address[] calldata _validators) external {
		for (uint i = 0; i < _validators.length; i++) {
			_addValidator(_validators[i]);
		}
	}

	function removeValidator(address _validator) external {
		require(isValidator[_validator], "Validator not found");

		for (uint i = 0; i < validators.length; i++) {
			if (validators[i] == _validator) {
				validators[i] = validators[validators.length - 1];
				validators.pop();
				isValidator[_validator] = false;
				break;
			}
		}
	}

	// Function used in ConsensusMain for getting a single validator
	function getActivatorForTx(
		address _recipient,
		bytes32 _randomSeed
	) external view returns (address) {
		require(validators.length > 0, "No validators available");
		uint256 randomIndex = uint256(_randomSeed) % validators.length;
		return validators[randomIndex];
	}

	// Function used in ConsensusMain for getting validator list
	function getValidatorsForTx(
		bytes32 _tx_id,
		bytes32 _randomSeed
	) external view returns (address[] memory) {
		return validators;
	}

	// Helper function to get total validator count
	function getValidatorCount() external view returns (uint256) {
		return validators.length;
	}
}
