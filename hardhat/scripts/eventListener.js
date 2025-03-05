const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

async function main() {
    const provider = new ethers.WebSocketProvider("ws://localhost:8545");

    provider.on("block", async (blockNumber) => {
        console.log("New block:", blockNumber);

        const block = await provider.getBlock(blockNumber);
        console.log("Timestamp:", new Date(block.timestamp * 1000));
        console.log("Transactions:", block.transactions.length);
    });

    provider.on("pending", async (txHash) => {
        console.log("New pending transaction:", txHash);
        const tx = await provider.getTransaction(txHash);
        console.log("Details:", tx);
    });

    process.on('SIGINT', () => {
        console.log('Closing listener...');
        provider.removeAllListeners();
        process.exit();
    });
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});