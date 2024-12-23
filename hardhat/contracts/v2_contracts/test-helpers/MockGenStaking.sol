// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

error NoValidatorsAvailable();
error NotEnoughValidators();
error ZeroTotalWeight();

contract MockGenStaking {
	address public owner;
	address[] public validators;
	address[] public topStakersHot;
	address[] public previousTopStakersHot;
	uint256[] public accumulatedWeights;
	uint256[] public previousAccumulatedWeights;
	uint256 public topStakersTotalWeight;
	uint256 public previousTopStakersTotalWeight;
	mapping(address => bool) public isValidator;

	// a bit longer than the real one to make sure we don't get any edge cases
	uint256 public FINALIZATION_INTERVAL = 1 hours + 10 minutes;

	struct ValidatorBan {
		bool isBanned;
		uint256 banEndTime;
	}

	mapping(address => ValidatorBan) public validatorBans;
	mapping(address => address) public hotToColdWallet;
	mapping(address => address) public coldToHotWallet;

	constructor(address _initialValidator) {
		owner = msg.sender;
		// _addValidator(_initialValidator);
	}

	function _addValidator(address _validator) private {
		if (!isValidator[_validator]) {
			validators.push(_validator);
			topStakersHot.push(_validator);
			previousTopStakersHot.push(_validator);
			isValidator[_validator] = true;

			// Set up hot/cold wallet mappings where both are the same address
			hotToColdWallet[_validator] = _validator;
			coldToHotWallet[_validator] = _validator;

			uint256 newWeight;
			if (accumulatedWeights.length == 0) {
				// If this is the first validator, start with 100 GEN (reduced from 2000 to prevent overflow)
				newWeight = 100 * 1e18;
			} else {
				// For subsequent validators, subtract 1 GEN from the last weight
				uint256 lastWeight = accumulatedWeights[
					accumulatedWeights.length - 1
				];
				newWeight = lastWeight > 1e18 ? lastWeight - 1e18 : 0;
			}

			uint256 cumulativeWeight = newWeight;
			if (accumulatedWeights.length > 0) {
				cumulativeWeight += accumulatedWeights[
					accumulatedWeights.length - 1
				];
			}

			accumulatedWeights.push(cumulativeWeight);
			previousAccumulatedWeights.push(cumulativeWeight);

			// Update total weights based on the new cumulative weight
			topStakersTotalWeight = cumulativeWeight;
			previousTopStakersTotalWeight = cumulativeWeight;
		}
	}

	function addValidators(address[] calldata _newValidators) external {
		uint256 cumulativeWeight = 0;

		// Process each validator
		for (uint256 i = 0; i < _newValidators.length; i++) {
			address validator = _newValidators[i];
			if (!isValidator[validator]) {
				validators.push(validator);
				topStakersHot.push(validator);
				previousTopStakersHot.push(validator);
				isValidator[validator] = true;

				// Calculate weight for this validator - weight decreases with index
				// Using smaller numbers to prevent overflow
				uint256 weight = i < 5 ? (5 - i) * 1e17 : 1e16;
				cumulativeWeight += weight;

				accumulatedWeights.push(cumulativeWeight);
				previousAccumulatedWeights.push(cumulativeWeight);
			}
		}

		topStakersTotalWeight = cumulativeWeight;
		previousTopStakersTotalWeight = cumulativeWeight;
	}

	function removeValidator(address _validator) external {
		require(isValidator[_validator], "Validator not found");

		for (uint256 i = 0; i < validators.length; i++) {
			if (validators[i] == _validator) {
				validators[i] = validators[validators.length - 1];
				validators.pop();
				isValidator[_validator] = false;

				// Update weights
				if (i < accumulatedWeights.length) {
					uint256 removedWeight = i == 0
						? accumulatedWeights[0]
						: accumulatedWeights[i] - accumulatedWeights[i - 1];
					topStakersTotalWeight -= removedWeight;
					previousTopStakersTotalWeight -= removedWeight;
				}
				break;
			}
		}
	}

	// Function used in ConsensusMain for getting a single validator
	function getActivatorForTx(
		address _recipient,
		bytes32 _randomSeed
	) external view returns (address) {
		if (validators.length == 0) revert NoValidatorsAvailable();
		uint256 randomIndex = uint256(_randomSeed) % validators.length;
		return validators[randomIndex];
	}

	// Function used in ConsensusMain for getting a single validator
	function getActivatorForSeed(
		bytes32 _randomSeed,
		uint256 timestamp
	) external view returns (address) {
		if (validators.length == 0) revert NoValidatorsAvailable();
		uint256 randomIndex = uint256(_randomSeed) % validators.length;
		return validators[randomIndex];
	}

	function getValidatorsLen(uint256 timestamp) public view returns (uint256) {
		return previousTopStakersHot.length;
	}

	function getValidatorsLenExternal(
		uint256 timestamp
	) external view returns (uint256) {
		return previousTopStakersHot.length;
	}

	function getValidatorsItem(
		uint256 timestamp,
		uint256 index
	) public view returns (address) {
		if (index >= previousTopStakersHot.length) return address(0);
		return previousTopStakersHot[index];
	}

	function getAccumWeightItem(
		uint256 timestamp,
		uint256 index
	) public view returns (uint256) {
		require(
			index < previousAccumulatedWeights.length,
			"Index out of bounds"
		);
		return previousAccumulatedWeights[index];
	}

	// Helper function to get total validator count
	function getValidatorCount() external view returns (uint256) {
		return previousTopStakersHot.length;
	}

	function getValidatorsForTx(
		bytes32 _tx_id,
		bytes32 _randomSeed,
		uint256 timestamp,
		uint256 requestedValidatorsCount,
		address[] memory consumedValidators
	) external view returns (address[] memory _validators) {
		uint256 maxValidators = getValidatorsLen(timestamp);
		if (maxValidators == 0) {
			revert NoValidatorsAvailable();
		}

		// If we request more validators than are available, revert.
		if (requestedValidatorsCount > maxValidators) {
			revert NotEnoughValidators();
		}

		uint256 alreadyConsumedCount = consumedValidators.length;
		uint256 nonConsumedCount = maxValidators - alreadyConsumedCount;

		// If the number of requested validators is greater or equal to the number
		// of non-consumed validators, simply return all non-consumed, non-banned validators.
		if (requestedValidatorsCount >= nonConsumedCount) {
			return
				_getAllNonConsumedValidators(
					timestamp,
					consumedValidators,
					maxValidators
				);
		}

		// Otherwise, we select validators randomly based on their stake weights.
		uint256 totalWeight = _getCurrentTotalWeight(timestamp);
		if (totalWeight == 0) {
			revert ZeroTotalWeight();
		}

		return
			_selectValidatorsRandomly(
				timestamp,
				_randomSeed,
				requestedValidatorsCount,
				consumedValidators,
				totalWeight,
				maxValidators
			);
	}

	function _getAllNonConsumedValidators(
		uint256 timestamp,
		address[] memory consumedValidators,
		uint256 maxValidators
	) internal view returns (address[] memory) {
		address[] memory validators = new address[](
			maxValidators - consumedValidators.length
		);
		uint256 index = 0;

		for (uint256 i = 0; i < maxValidators; i++) {
			address validatorHot = getValidatorsItem(timestamp, i);
			address coldWallet = hotToColdWallet[validatorHot];

			if (
				!_isConsumed(validatorHot, consumedValidators) &&
				!validatorBans[coldWallet].isBanned
			) {
				validators[index] = validatorHot;
				index++;
			}
		}

		return validators;
	}

	function _getCurrentTotalWeight(
		uint256 timestamp
	) internal view returns (uint256) {
		// If the timestamp is older than FINALIZATION_INTERVAL from the current block,
		// use the previous total weight; otherwise, use the current total.
		if (timestamp < block.timestamp - FINALIZATION_INTERVAL) {
			return previousTopStakersTotalWeight;
		} else {
			return topStakersTotalWeight;
		}
	}

	function _selectValidatorsRandomly(
		uint256 timestamp,
		bytes32 _randomSeed,
		uint256 numValidators,
		address[] memory consumedValidators,
		uint256 totalWeight,
		uint256 maxValidators
	) internal view returns (address[] memory selectedValidators) {
		selectedValidators = new address[](numValidators);
		bool[] memory isSelected = new bool[](maxValidators);

		for (uint256 i = 0; i < numValidators; i++) {
			// Generate a pseudo-random stake for selection.
			uint256 randomStake = _generateRandomStake(
				_randomSeed,
				consumedValidators.length + i,
				i + 1,
				totalWeight
			);
			uint256 validatorIndex = _findValidatorIndexByWeight(
				timestamp,
				randomStake,
				maxValidators
			);

			// Find the next eligible validator (non-consumed, non-banned, not already selected).
			address validator = _findNextEligibleValidator(
				timestamp,
				validatorIndex,
				consumedValidators,
				isSelected,
				maxValidators
			);

			if (validator == address(0)) {
				revert("No valid validator found");
			}

			selectedValidators[i] = validator;
		}

		return selectedValidators;
	}

	function _generateRandomStake(
		bytes32 _randomSeed,
		uint256 offset,
		uint256 multiplier,
		uint256 totalWeight
	) internal pure returns (uint256) {
		// Combine seed with offset to generate a unique pseudo-random value
		// and then modulo by totalWeight to choose a random stake position.
		uint256 combinedSeed = uint256(
			keccak256(abi.encodePacked(_randomSeed, offset))
		);
		unchecked {
			return (combinedSeed * multiplier) % totalWeight;
		}
	}

	function _findValidatorIndexByWeight(
		uint256 timestamp,
		uint256 randomStake,
		uint256 maxValidators
	) internal view returns (uint256) {
		// Binary search to find the appropriate validator index for the given randomStake.
		uint256 low = 0;
		uint256 high = maxValidators - 1;
		while (low <= high) {
			uint256 mid = (low + high) >> 1;
			uint256 midWeight = getAccumWeightItem(timestamp, mid);

			if (midWeight > randomStake) {
				// If this midWeight surpasses randomStake and is the first such occurrence, we settle here.
				if (mid == 0) {
					return mid;
				}
				high = mid - 1;
			} else {
				low = mid + 1;
			}
		}

		// If not found directly (due to how we adjust low/high),
		// high will represent the last suitable validator index.
		return high;
	}

	function _findNextEligibleValidator(
		uint256 timestamp,
		uint256 startIndex,
		address[] memory consumedValidators,
		bool[] memory isSelected,
		uint256 maxValidators
	) internal view returns (address) {
		uint256 originalIndex = startIndex;

		for (uint256 attempt = 0; attempt < maxValidators; attempt++) {
			address validatorHot = getValidatorsItem(timestamp, startIndex);
			address coldWallet = hotToColdWallet[validatorHot];

			// If validator is consumed, banned or already selected, move to the next.
			if (
				_isConsumed(validatorHot, consumedValidators) ||
				validatorBans[coldWallet].isBanned ||
				isSelected[startIndex]
			) {
				startIndex = (startIndex + 1) % maxValidators;
				// If we've looped around back to the original index, no suitable validator is found.
				if (startIndex == originalIndex) break;
				continue;
			}

			// Mark as selected and return
			isSelected[startIndex] = true;
			return validatorHot;
		}

		// No valid validator found after trying all possible indices.
		return address(0);
	}

	function _isConsumed(
		address validator,
		address[] memory consumedValidators
	) internal pure returns (bool) {
		for (uint256 k = 0; k < consumedValidators.length; k++) {
			if (consumedValidators[k] == validator) {
				return true;
			}
		}
		return false;
	}
}