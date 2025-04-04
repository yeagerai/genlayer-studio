// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "./utils/RandomnessUtils.sol";
import "./utils/Errors.sol";

contract ConsensusManager is
	Initializable,
	Ownable2StepUpgradeable,
	ReentrancyGuardUpgradeable,
	AccessControlUpgradeable
{
	address public genConsensus;
	mapping(address => bytes32) public recipientRandomSeed;

	receive() external payable {}

	function initialize() public initializer {
		__Ownable2Step_init();
		__ReentrancyGuard_init();
		__AccessControl_init();
	}

	function updateRandomSeedForRecipient(
		address _recipient,
		address _sender,
		bytes calldata _vrfProof
	) external returns (bytes32 newRandomSeed) {
		bytes32 randomSeed = recipientRandomSeed[_recipient];
		newRandomSeed = bytes32(
			RandomnessUtils.updateRandomSeed(
				_vrfProof,
				uint256(randomSeed),
				_sender
			)
		);
		recipientRandomSeed[_recipient] = newRandomSeed;
	}

	function addNewRandomSeedForRecipient(
		address _recipient,
		bytes32 _randomSeed
	) external {
		if (recipientRandomSeed[_recipient] != bytes32(0)) {
			revert Errors.RandomSeedAlreadySet();
		}
		recipientRandomSeed[_recipient] = _randomSeed;
	}
}