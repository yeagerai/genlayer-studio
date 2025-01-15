// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

contract GhostContract {
    // Define an event
    event ReceivedData(bytes data);

    // Fallback function logs any raw data received
    fallback() external payable {
        emit ReceivedData(msg.data); // Logs the data in a blockchain event
    }
}

