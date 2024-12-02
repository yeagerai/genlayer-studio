// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IGenLayerStaking {
	function stake() external payable;
	function unstake(uint256 amount) external;
	function delegate(address validator) external;
	function undelegate() external;
	function balanceOfBase(address account) external view returns (uint256);
	function setHotWallet(address hotWallet) external;
	function claim() external;
	function accumulateTxFeeRewards(
		uint256 txFeeAmount,
		address[] memory validators
	) external;
	function getInflationOverSeconds(
		uint256 secs
	) external view returns (uint256);
}
