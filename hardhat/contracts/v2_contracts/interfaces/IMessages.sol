// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IMessages {
	struct SubmittedMessage {
		address recipient;
		bool externalMessage;
		bool onAcceptance;
		bytes message;
	}

	function emitMessagesOnAcceptance(bytes32 _tx_id) external;

	function emitMessagesOnFinalization(bytes32 _tx_id) external;
}