const hre = require("hardhat");
const fs = require('fs');
const path = require('path');

async function getAccountBalance(address) {
  try {
    const balance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
    return parseInt(balance, 16);
  } catch (error) {
    console.error(`Error getting balance for ${address}:`, error);
    return "0";
  }
}

async function main() {
  try {
    console.log(`[${new Date().toISOString()}] Starting snapshot process...`);

    // Wait for any pending transactions to be mined
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Get current block number using the correct method
    const blockNumber = await hre.network.provider.send("eth_blockNumber");
    const blockNumberDec = parseInt(blockNumber, 16);

    // Get the latest block details
    const latestBlock = await hre.network.provider.send("eth_getBlockByNumber", ["latest", true]);

    // Get accounts using the correct method
    const accounts = await hre.network.provider.send("eth_accounts");

    // Get network information
    const chainId = await hre.network.provider.send("eth_chainId");
    const gasPrice = await hre.network.provider.send("eth_gasPrice");

    // Take a snapshot of the current state
    const snapshotId = await hre.network.provider.send("evm_snapshot");
    console.log(`[${new Date().toISOString()}] Snapshot taken successfully with ID: ${snapshotId}`);

    // Create timestamp for the snapshot file
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

    // Get all deployments using hardhat-deploy
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

    // Read all deployment files from the deployment directory
    const deploymentDir = path.join(__dirname, '../deployments/genlayer_network');
    const deploymentFiles = fs.readdirSync(deploymentDir).filter(file => file.endsWith('.json'));

    // console.log(`[${new Date().toISOString()}] Found ${deploymentFiles.length} deployment files`);

    // Process all deployment files
    for (const file of deploymentFiles) {
      const contractName = file.replace('.json', '');
      try {
        // Read deployment file directly to get all data including bytecode
        const deploymentPath = path.join(deploymentDir, file);
        const deploymentData = JSON.parse(fs.readFileSync(deploymentPath, 'utf8'));

        // Verify contract exists on chain and get current bytecode
        const address = deploymentData.address;
        const currentCode = await hre.network.provider.send("eth_getCode", [address, "latest"]);

        if (currentCode === '0x' || currentCode === '') {
          /// console.log(`[${new Date().toISOString()}] Warning: Contract ${contractName} at ${address} has no bytecode!`);
          continue;
        }

        // Store the complete deployment data
        deployments[contractName] = {
          address: address,
          abi: deploymentData.abi,
          bytecode: deploymentData.bytecode,
          deployedBytecode: deploymentData.deployedBytecode
        };

        // console.log(`[${new Date().toISOString()}] Saved deployment info for ${contractName} at ${address}`);
      } catch (error) {
        console.error(`[${new Date().toISOString()}] Error processing ${contractName}:`, error);
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

    // Build contract address mapping for quick access
    const contractAddresses = {};
    for (const [name, deployment] of Object.entries(deployments)) {
      contractAddresses[name] = deployment.address;
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
      contracts: contractAddresses
    };

    // Create snapshots directory if it doesn't exist
    const snapshotsDir = path.join(__dirname, '../snapshots');
    if (!fs.existsSync(snapshotsDir)) {
      fs.mkdirSync(snapshotsDir, { recursive: true });
    }

    // Save the snapshot with timestamp
    const snapshotPath = path.join(snapshotsDir, `snapshot-${timestamp}.json`);
    fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));

    // Update the latest.json to point to this snapshot
    const latestPath = path.join(snapshotsDir, 'latest.json');
    fs.writeFileSync(latestPath, JSON.stringify({
      ...snapshotData,
      file: `snapshot-${timestamp}.json`
    }, null, 2));

    // console.log(`[${new Date().toISOString()}] Snapshot saved with ${Object.keys(deployments).length} contracts and ${accounts.length} accounts`);
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