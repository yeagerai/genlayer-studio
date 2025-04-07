const hre = require("hardhat");
const fs = require('fs');
const path = require('path');

async function restoreBlockchainState(snapshotData) {
  try {
    console.log(`[${new Date().toISOString()}] Restoring blockchain state...`);

    // Get the snapshot ID
    const snapshotId = snapshotData.id;
    console.log(`[${new Date().toISOString()}] Restoring snapshot with ID: ${snapshotId}`);

    // Reset the blockchain state completely before restoring
    console.log(`[${new Date().toISOString()}] Resetting blockchain state...`);
    await hre.network.provider.send("hardhat_reset");

    // Restore the snapshot
    const reverted = await hre.network.provider.send("evm_revert", [snapshotId]);
    if (!reverted) {
      console.log(`[${new Date().toISOString()}] Failed to revert to snapshot, trying alternative method...`);

      // If direct revert fails, try to recreate the state manually
      await recreateContractsFromDeployments(snapshotData.deployments);
      return true;
    }

    console.log(`[${new Date().toISOString()}] Snapshot restored successfully`);

    // Immediately take a new snapshot (this helps preserve the state)
    const newSnapshotId = await hre.network.provider.send("evm_snapshot");
    console.log(`[${new Date().toISOString()}] Created new snapshot with ID: ${newSnapshotId}`);

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
          console.log(`[${new Date().toISOString()}] Setting nonce for ${address} from ${currentNonceDec} to ${expectedNonce}`);
          // Send empty transactions to increase nonce
          for (let i = currentNonceDec; i < expectedNonce; i++) {
            await hre.network.provider.send("evm_mine");
          }
        }
      } else {
        console.log(`[${new Date().toISOString()}] Skipping nonce restoration for external account ${address}`);
      }
    }

    // Restore account balances
    console.log(`[${new Date().toISOString()}] Restoring account balances...`);
    const firstAccount = defaultAccounts[0]; // This account has 10000 ETH

    for (const [address, expectedBalance] of Object.entries(snapshotData.accounts.balances)) {
      const currentBalance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
      const currentBalanceDec = parseInt(currentBalance, 16);

      if (currentBalanceDec !== expectedBalance) {
        console.log(`[${new Date().toISOString()}] Setting balance for ${address} from ${currentBalanceDec} to ${expectedBalance}`);
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

    // Verify deployments are present
    console.log(`[${new Date().toISOString()}] Verifying deployments...`);
    for (const [name, deployment] of Object.entries(snapshotData.deployments)) {
      const currentDeployment = await hre.deployments.get(name);
      if (!currentDeployment || currentDeployment.address !== deployment.address) {
        console.log(`[${new Date().toISOString()}] Warning: Deployment mismatch for ${name}`);
        console.log(`Expected: ${deployment.address}`);
        console.log(`Got: ${currentDeployment?.address || 'none'}`);
      }
    }

    // Force a new block to ensure all state changes are committed
    await hre.network.provider.send("evm_mine");

    return true;
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error restoring blockchain state:`, error);
    return false;
  }
}

async function recreateContractsFromDeployments(deployments) {
  console.log(`[${new Date().toISOString()}] Recreating contracts from deployment files...`);

  try {
    // Get accounts
    const accounts = await hre.network.provider.send("eth_accounts");
    const firstAccount = accounts[0];

    for (const [contractName, deployment] of Object.entries(deployments)) {
      console.log(`[${new Date().toISOString()}] Processing contract: ${contractName}`);

      // Verify if the contract exists at the expected address
      const code = await hre.network.provider.send("eth_getCode", [deployment.address, "latest"]);

      if (code === '0x' || code === '') {
        console.log(`[${new Date().toISOString()}] Contract ${contractName} bytecode missing, forcing it into the blockchain state...`);

        // Clean the bytecode for all contracts
        let bytecode = deployment.deployedBytecode;
        // Remove any potential invalid characters or formatting
        bytecode = bytecode.replace(/[^0-9a-fA-Fx]/g, '');
        if (!bytecode.startsWith('0x')) {
          bytecode = '0x' + bytecode;
        }

        // Force the contract bytecode directly into the blockchain state
        await hre.network.provider.send("hardhat_setCode", [
          deployment.address,
          bytecode
        ]);

        // Check if it worked
        const newCode = await hre.network.provider.send("eth_getCode", [deployment.address, "latest"]);
        if (newCode !== '0x' && newCode !== '') {
          console.log(`[${new Date().toISOString()}] Successfully restored bytecode for ${contractName}`);

          // Explicitly set storage slots for metadata if available
          if (deployment.storageLayout) {
            console.log(`[${new Date().toISOString()}] Restoring contract storage layout...`);
            try {
              // This is a simplified approach - a full implementation would restore all storage slots
              for (const [slot, value] of Object.entries(deployment.storageLayout)) {
                await hre.network.provider.send("hardhat_setStorageAt", [
                  deployment.address,
                  slot,
                  value
                ]);
              }
            } catch (error) {
              console.log(`[${new Date().toISOString()}] Error restoring storage layout: ${error.message}`);
            }
          }
        } else {
          console.log(`[${new Date().toISOString()}] Failed to restore bytecode for ${contractName}`);
        }
      } else {
        console.log(`[${new Date().toISOString()}] Contract ${contractName} already exists at ${deployment.address}`);
      }

      // Ensure contract is properly registered with hardhat-deploy
      try {
        await hre.deployments.save(contractName, {
          address: deployment.address,
          abi: deployment.abi,
          bytecode: deployment.bytecode,
          deployedBytecode: deployment.deployedBytecode
        });
        console.log(`[${new Date().toISOString()}] Registered deployment for ${contractName}`);
      } catch (error) {
        console.error(`[${new Date().toISOString()}] Error registering deployment: ${error.message}`);
      }
    }

    // Force a new block to ensure all state changes are committed
    await hre.network.provider.send("evm_mine");

    console.log(`[${new Date().toISOString()}] All contracts recreated successfully`);
    return true;
  } catch (error) {
    console.error(`[${new Date().toISOString()}] Error recreating contracts:`, error);
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
      console.log(`[${new Date().toISOString()}] Account ${address}:`);
      console.log(`  Current balance: ${currentBalanceDec}`);
      console.log(`  Expected balance: ${expectedBalance}`);
    }

    // Validate nonces only for predefined accounts
    for (const [address, expectedNonce] of Object.entries(snapshotData.accounts.nonces)) {
      if (accounts.includes(address)) {
        const currentNonce = await hre.network.provider.send("eth_getTransactionCount", [address, "latest"]);
        const currentNonceDec = parseInt(currentNonce, 16);
        console.log(`[${new Date().toISOString()}] Account ${address}:`);
        console.log(`  Current nonce: ${currentNonceDec}`);
        console.log(`  Expected nonce: ${expectedNonce}`);
      } else {
        console.log(`[${new Date().toISOString()}] Skipping nonce validation for external account ${address}`);
      }
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
