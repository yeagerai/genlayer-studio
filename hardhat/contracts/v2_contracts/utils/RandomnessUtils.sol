// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

library RandomnessUtils {
	using ECDSA for bytes32;

	/**
	 * @dev Updates a random seed by verifying a VRF proof signature and generating a new seed.
	 * @param vrfProof The signature proof provided by the signer
	 * @param currentSeed The current seed value to be used for verification
	 * @param signer The address that should have signed the message
	 * @return newSeed The newly generated random seed
	 */
	function updateRandomSeed(
		bytes memory vrfProof,
		uint256 currentSeed,
		address signer
	) internal pure returns (uint256) {
		// Convert seed to bytes32 and create ethereum signed message hash
		bytes32 seed = bytes32(currentSeed);
		bytes32 hash = MessageHashUtils.toEthSignedMessageHash(seed);

		// Verify the signature
		address recoveredSigner = hash.recover(vrfProof);
		// Comment next check if you want to skip signature verification
		require(
			recoveredSigner == signer,
			"RandomnessUtils: Invalid signature"
		);

		// Generate and return new seed
		return uint256(keccak256(vrfProof));
	}
}