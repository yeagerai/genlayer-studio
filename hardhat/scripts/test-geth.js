const { ethers } = require("hardhat");

async function main() {
  console.log("Connecting to local Geth node...");

  // Get accounts
  const accounts = await ethers.getSigners();
  console.log("Main account:", accounts[0].address);

  // Get balance
  const balance = await ethers.provider.getBalance(accounts[0].address);
  console.log("Balance:", ethers.formatEther(balance), "ETH");

  // Get current block number
  const blockNumber = await ethers.provider.getBlockNumber();
  console.log("Current block:", blockNumber);

  // Send a simple transaction
  console.log("Sending test transaction...");
  const tx = await accounts[0].sendTransaction({
    to: accounts[1].address,
    value: ethers.parseEther("1.0")
  });

  console.log("Transaction sent:", tx.hash);
  console.log("Waiting for confirmation...");
  await tx.wait();
  console.log("Transaction confirmed!");

  // Verify new balance
  const newBalance = await ethers.provider.getBalance(accounts[1].address);
  console.log("New balance of account 2:", ethers.formatEther(newBalance), "ETH");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });