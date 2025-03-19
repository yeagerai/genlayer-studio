// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

interface IGenLayerToken is IERC20 {
	function mint(address account, uint256 amount) external;
	function burn(uint256 amount) external;
	function setTimelockFactory(address _timelockFactory) external;
	function getInflationOverSeconds(
		uint256 secs
	) external view returns (uint256);
}