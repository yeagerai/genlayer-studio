// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGenManager {
	/// @notice Checks if a given address is a registered GenVM contract
	/// @param contractAddress The address to check
	/// @return bool True if the address is a GenVM contract, false otherwise
	function isGenVMContract(
		address contractAddress
	) external view returns (bool);
}
