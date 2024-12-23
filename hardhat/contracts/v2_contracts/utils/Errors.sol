// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

library Errors {
	error NonGenVMContract();
	error TransactionNotProposing();
	error CallerNotActivator();
	error CallerNotLeader();
	error CallerNotValidator();
	error CallerNotMessages();
	error TransactionNotCommitting();
	error VoteAlreadyCommitted();
	error TransactionNotRevealing();
	error VoteAlreadyRevealed();
	error InvalidVote();
	error TransactionNotAcceptedOrUndetermined();
	error CanNotAppeal();
	error AppealBondTooLow();
}