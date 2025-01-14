// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IMessages {
	enum MessageType {
		External,
		Internal
	}

	struct SubmittedMessage {
		MessageType messageType;
		address recipient;
		uint256 value;
		bytes data;
		bool onAcceptance; // true = on acceptance, false = on finalization
	}

	function executeMessage(IMessages.SubmittedMessage memory message) external;

	function emitMessagesOnAcceptance(bytes32 _tx_id) external;

	function emitMessagesOnFinalization(bytes32 _tx_id) external;
}