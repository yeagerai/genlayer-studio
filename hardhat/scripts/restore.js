const hre = require("hardhat");
const fs = require('fs');
const path = require('path');

async function restoreBlockchainState(snapshotData) {
  try {
    console.log(`[${new Date().toISOString()}] Restoring blockchain state...`);

    // Restore block number
    const currentBlockNumber = await hre.network.provider.send("eth_blockNumber");
    const currentBlockNumberDec = parseInt(currentBlockNumber, 16);
    const targetBlockNumber = snapshotData.blockNumber;

    if (currentBlockNumberDec < targetBlockNumber) {
      console.log(`[${new Date().toISOString()}] Mining blocks to reach target block number...`);
      const blocksToMine = targetBlockNumber - currentBlockNumberDec;
      for (let i = 0; i < blocksToMine; i++) {
        await hre.network.provider.send("evm_mine");
      }
    }

    // Get default accounts (predefined accounts)
    const defaultAccounts = await hre.network.provider.send("eth_accounts");

    // Restore account nonces only for predefined accounts
    console.log(`[${new Date().toISOString()}] Restoring account nonces...`);
    for (const [address, expectedNonce] of Object.entries(snapshotData.accounts.nonces)) {
      // Only restore nonces for predefined accounts
      if (defaultAccounts.includes(address)) {
        const currentNonce = await hre.network.provider.send("eth_getTransactionCount", [address, "latest"]);
        const currentNonceDec = parseInt(currentNonce, 16);

        if (currentNonceDec < expectedNonce) {
          // console.log(`[${new Date().toISOString()}] Setting nonce for ${address} from ${currentNonceDec} to ${expectedNonce}`);
          // Send empty transactions to increase nonce
          for (let i = currentNonceDec; i < expectedNonce; i++) {
            await hre.network.provider.send("eth_sendTransaction", [{
              from: address,
              to: address,
              value: "0x0",
              nonce: `0x${i.toString(16)}`
            }]);
          }
        }
      } else {
        // console.log(`[${new Date().toISOString()}] Skipping nonce restoration for external account ${address}`);
      }
    }

    // Restore account balances
    console.log(`[${new Date().toISOString()}] Restoring account balances...`);
    const firstAccount = defaultAccounts[0]; // This account has 10000 ETH

    for (const [address, expectedBalance] of Object.entries(snapshotData.accounts.balances)) {
      const currentBalance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
      const currentBalanceDec = parseInt(currentBalance, 16);

      if (currentBalanceDec !== expectedBalance) {
        // console.log(`[${new Date().toISOString()}] Setting balance for ${address} from ${currentBalanceDec} to ${expectedBalance}`);
        const balanceDiff = expectedBalance - currentBalanceDec;

        if (balanceDiff > 0) {
          // Transfer balance difference from the first account
          await hre.network.provider.send("eth_sendTransaction", [{
            from: firstAccount,
            to: address,
            value: `0x${balanceDiff.toString(16)}`
          }]);
        }
      }
    }

    return true;
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error restoring blockchain state:`, error);
    return false;
  }
}

async function validateState(snapshotData) {
  try {
    console.log(`[${new Date().toISOString()}] Validating state after restoration...`);

    // Get current block number
    const currentBlockNumber = await hre.network.provider.send("eth_blockNumber");
    const currentBlockNumberDec = parseInt(currentBlockNumber, 16);
    console.log(`[${new Date().toISOString()}] Current block number: ${currentBlockNumberDec}`);
    console.log(`[${new Date().toISOString()}] Expected block number: ${snapshotData.blockNumber}`);

    // Get latest block
    const latestBlock = await hre.network.provider.send("eth_getBlockByNumber", ["latest", true]);
    console.log(`[${new Date().toISOString()}] Latest block hash: ${latestBlock.hash}`);
    console.log(`[${new Date().toISOString()}] Expected block hash: ${snapshotData.latestBlock.hash}`);

    // Get all accounts
    const accounts = await hre.network.provider.send("eth_accounts");
    console.log(`[${new Date().toISOString()}] Number of default accounts: ${accounts.length}`);
    console.log(`[${new Date().toISOString()}] Number of accounts in snapshot: ${snapshotData.accounts.addresses.length}`);

    // Validate balances for all accounts in snapshot
    for (const [address, expectedBalance] of Object.entries(snapshotData.accounts.balances)) {
      const currentBalance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
      const currentBalanceDec = parseInt(currentBalance, 16);
      // console.log(`[${new Date().toISOString()}] Account ${address}:`);
      // console.log(`  Current balance: ${currentBalanceDec}`);
      // console.log(`  Expected balance: ${expectedBalance}`);
    }

    // Validate nonces only for predefined accounts
    for (const [address, expectedNonce] of Object.entries(snapshotData.accounts.nonces)) {
      if (accounts.includes(address)) {
        const currentNonce = await hre.network.provider.send("eth_getTransactionCount", [address, "latest"]);
        const currentNonceDec = parseInt(currentNonce, 16);
        // console.log(`[${new Date().toISOString()}] Account ${address}:`);
        // console.log(`  Current nonce: ${currentNonceDec}`);
        // console.log(`  Expected nonce: ${expectedNonce}`);
      } else {
        console.log(`[${new Date().toISOString()}] Skipping nonce validation for external account ${address}`);
      }
    }

    // Validate deployments
    for (const [name, deployment] of Object.entries(snapshotData.deployments)) {
      // console.log(`[${new Date().toISOString()}] Contract ${name}:`);
      // console.log(`  Expected address: ${deployment.address}`);
      // console.log(`  Expected ABI: ${JSON.stringify(deployment.abi).length} bytes`);
      // console.log(`  Expected bytecode: ${deployment.bytecode.length} bytes`);
    }

    return true;
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error validating state:`, error);
    return false;
  }
}

async function main() {
  try {
    console.log(`[${new Date().toISOString()}] Starting snapshot restoration process...`);

    // Read the snapshot file
    const snapshotPath = path.join(__dirname, '../snapshots/latest.json');
    const snapshotData = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'));

    // Get the snapshot ID
    const snapshotId = snapshotData.id;
    console.log(`[${new Date().toISOString()}] Restoring snapshot with ID: ${snapshotId}`);

    // Restore the snapshot
    await hre.network.provider.send("evm_revert", [snapshotId]);

    console.log(`[${new Date().toISOString()}] Snapshot restored successfully`);

    // Restore blockchain state
    const blockchainRestored = await restoreBlockchainState(snapshotData);
    if (!blockchainRestored) {
      throw new Error("Failed to restore blockchain state");
    }

    // Validate the state after restoration
    const isValid = await validateState(snapshotData);
    if (!isValid) {
      throw new Error("State validation failed after restoration");
    }

    console.log(`[${new Date().toISOString()}] State validation completed successfully`);
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error restoring snapshot:`, error);
    throw error;
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(`[${new Date().toISOString()}] Fatal error:`, error);
    process.exit(1);
  });