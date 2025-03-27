const hre = require("hardhat");
const fs = require('fs');
const path = require('path');

async function loadDeployment(name) {
  try {
    const deploymentPath = path.join(__dirname, '../deployments/localhost', `${name}.json`);
    if (fs.existsSync(deploymentPath)) {
      return JSON.parse(fs.readFileSync(deploymentPath, 'utf8'));
    }
    return null;
  } catch (error) {
    console.error(`Error loading deployment for ${name}:`, error);
    return null;
  }
}

async function getAccountBalance(address) {
  try {
    const balance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
    return parseInt(balance, 16);
  } catch (error) {
    console.error(`Error getting balance for ${address}:`, error);
    return "0";
  }
}

async function getAllAccounts() {
  try {
    // Get the default accounts
    const defaultAccounts = await hre.network.provider.send("eth_accounts");

    // Get the latest block
    const latestBlock = await hre.network.provider.send("eth_getBlockByNumber", ["latest", true]);

    // Extract unique addresses from transactions
    const uniqueAddresses = new Set(defaultAccounts);

    // Add addresses from transactions
    for (const tx of latestBlock.transactions) {
      if (tx.from) uniqueAddresses.add(tx.from);
      if (tx.to) uniqueAddresses.add(tx.to);
    }

    // Get previous blocks to find more addresses
    const currentBlockNumber = parseInt(latestBlock.number, 16);
    const startBlock = Math.max(0, currentBlockNumber - 100); // Look at last 100 blocks

    for (let i = startBlock; i <= currentBlockNumber; i++) {
      const block = await hre.network.provider.send("eth_getBlockByNumber", [`0x${i.toString(16)}`, true]);
      for (const tx of block.transactions) {
        if (tx.from) uniqueAddresses.add(tx.from);
        if (tx.to) uniqueAddresses.add(tx.to);
      }
    }

    return Array.from(uniqueAddresses);
  } catch (error) {
    console.error(`Error getting all accounts:`, error);
    return [];
  }
}

async function main() {
  try {
    // console.log(`[${new Date().toISOString()}] Starting snapshot process...`);

    // Wait for any pending transactions to be mined
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Get current block number using the correct method
    const blockNumber = await hre.network.provider.send("eth_blockNumber");
    const blockNumberDec = parseInt(blockNumber, 16);

    // Get the latest block details
    const latestBlock = await hre.network.provider.send("eth_getBlockByNumber", ["latest", true]);

    // Get all accounts that have interacted with the node
    const accounts = await getAllAccounts();
    // console.log(`[${new Date().toISOString()}] Found ${accounts.length} unique accounts`);

    // Get network information
    const chainId = await hre.network.provider.send("eth_chainId");
    const gasPrice = await hre.network.provider.send("eth_gasPrice");

    // Take a snapshot of the current state
    // console.log(`[${new Date().toISOString()}] Taking EVM snapshot...`);
    const snapshotId = await hre.network.provider.send("evm_snapshot");
    console.log(`[${new Date().toISOString()}] Snapshot taken successfully with ID: ${snapshotId}`);

    // Create timestamp for the snapshot file
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

    // Load all deployments
    const deployments = {};
    const contractNames = [
      "ConsensusMain",
      "ConsensusManager",
      "ConsensusData",
      "GhostContract",
      "GhostFactory",
      "GhostBlueprint",
      "MockGenStaking",
      "Queues",
      "Transactions",
      "Messages"
    ];

    for (const name of contractNames) {
      const deployment = await loadDeployment(name);
      if (deployment) {
        deployments[name] = deployment;
      }
    }

    // Get balances for all accounts
    const accountBalances = {};
    for (const account of accounts) {
      accountBalances[account] = await getAccountBalance(account);
    }

    // Get nonces for all accounts
    const accountNonces = {};
    for (const account of accounts) {
      const nonce = await hre.network.provider.send("eth_getTransactionCount", [account, "latest"]);
      accountNonces[account] = parseInt(nonce, 16);
    }

    const snapshotData = {
      id: snapshotId,
      timestamp: Date.now(),
      network: hre.network.name,
      chainId: parseInt(chainId, 16),
      blockNumber: blockNumberDec,
      latestBlock: {
        number: blockNumberDec,
        hash: latestBlock.hash,
        timestamp: parseInt(latestBlock.timestamp, 16),
        transactions: latestBlock.transactions.length,
        gasUsed: parseInt(latestBlock.gasUsed, 16),
        gasLimit: parseInt(latestBlock.gasLimit, 16)
      },
      gasPrice: parseInt(gasPrice, 16),
      accounts: {
        addresses: accounts,
        balances: accountBalances,
        nonces: accountNonces
      },
      deployments: deployments,
      // Include the original contracts mapping for backward compatibility
      contracts: {
        ConsensusMain: deployments.ConsensusMain?.address,
        ConsensusManager: deployments.ConsensusManager?.address,
        ConsensusData: deployments.ConsensusData?.address,
        GhostContract: deployments.GhostContract?.address,
        GhostFactory: deployments.GhostFactory?.address,
        GhostBlueprint: deployments.GhostBlueprint?.address,
        MockGenStaking: deployments.MockGenStaking?.address,
        Queues: deployments.Queues?.address,
        Transactions: deployments.Transactions?.address,
        Messages: deployments.Messages?.address
      }
    };

    // Save the snapshot with timestamp
    const snapshotPath = path.join(__dirname, '../snapshots', `snapshot-${timestamp}.json`);
    fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));

    // Update the latest.json to point to this snapshot
    const latestPath = path.join(__dirname, '../snapshots/latest.json');
    fs.writeFileSync(latestPath, JSON.stringify({
      ...snapshotData,
      file: `snapshot-${timestamp}.json`
    }, null, 2));

    // console.log(`[${new Date().toISOString()}] Snapshot data saved to ${snapshotPath}`);
    // console.log(`[${new Date().toISOString()}] Current block number: ${blockNumberDec}`);
    // console.log(`[${new Date().toISOString()}] Latest block hash: ${latestBlock.hash}`);
    // console.log(`[${new Date().toISOString()}] Transactions in latest block: ${latestBlock.transactions.length}`);
    // console.log(`[${new Date().toISOString()}] Gas used in latest block: ${parseInt(latestBlock.gasUsed, 16)}`);
    // console.log(`[${new Date().toISOString()}] Number of accounts: ${accounts.length}`);
    // console.log(`[${new Date().toISOString()}] Number of deployed contracts: ${Object.keys(deployments).length}`);
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error taking snapshot:`, error);
    throw error;
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(`[${new Date().toISOString()}] Fatal error:`, error);
    process.exit(1);
  });