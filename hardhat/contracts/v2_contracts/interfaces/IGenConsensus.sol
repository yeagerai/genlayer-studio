// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGenConsensus {
	function executeMessage(
		address _recipient,
		uint _value,
		bytes memory _data
	) external returns (bool success);
}