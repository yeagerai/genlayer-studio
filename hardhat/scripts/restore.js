const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

/**
 * Mina bloques hasta llegar al número de bloque objetivo
 * @param {number} targetBlock Número de bloque a alcanzar
 */
async function mineToBlock(targetBlock) {
  const currentHex = await hre.network.provider.send("eth_blockNumber");
  const currentDec = parseInt(currentHex, 16);
  const diff = targetBlock - currentDec;
  if (diff > 0) {
    console.log(`Mining ${diff} blocks to reach block ${targetBlock}...`);
    await hre.network.provider.send("hardhat_mine", [`0x${diff.toString(16)}`]);
  }
}

/**
 * Restores all contract relationships and settings from 001_deploy_fixture.js
 * @param {object} snapshotData Data from the snapshot
 */
async function restoreFixtureConfigurations(snapshotData) {
  console.log(`Restoring contract configurations from deploy fixture...`);

  try {
    const { deployments } = snapshotData;

    // Get signers - we need deployer (first account)
    const signers = await hre.ethers.getSigners();
    const deployer = signers[0];

    // First check which contracts we have
    const deployedContracts = {};
    for (const [name, data] of Object.entries(deployments)) {
      try {
        deployedContracts[name] = new hre.ethers.Contract(
          data.address,
          data.abi,
          deployer
        );
      } catch (error) {
        console.log(`Error creating contract instance for ${name}: ${error.message}`);
      }
    }

    // Initialize core contracts if needed
    const initializeContracts = async () => {
      // 1. Initialize GhostFactory
      if (deployedContracts.GhostFactory &&
          deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          // Check if already initialized by checking owner
          if (deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'owner')) {
            const owner = await deployedContracts.GhostFactory.owner();
            if (owner === "0x0000000000000000000000000000000000000000") {
              console.log(`Initializing GhostFactory...`);
              await deployedContracts.GhostFactory.initialize();
            }
          } else {
            // No way to check, try to initialize anyway
            try {
              await deployedContracts.GhostFactory.initialize();
            } catch (error) {
              // Likely already initialized, ignore
            }
          }
        } catch (error) {
          console.log(`GhostFactory initialization skipped: ${error.message}`);
        }
      }

      // 2. Initialize GhostBlueprint
      if (deployedContracts.GhostBlueprint &&
          deployedContracts.GhostBlueprint.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          // Check if already initialized
          if (deployedContracts.GhostBlueprint.interface.fragments.some(f => f.name === 'owner')) {
            const owner = await deployedContracts.GhostBlueprint.owner();
            if (owner === "0x0000000000000000000000000000000000000000") {
              console.log(`Initializing GhostBlueprint...`);
              await deployedContracts.GhostBlueprint.initialize(deployer.address);
            }
          } else {
            try {
              await deployedContracts.GhostBlueprint.initialize(deployer.address);
            } catch (error) {
              // Likely already initialized, ignore
            }
          }
        } catch (error) {
          console.log(`GhostBlueprint initialization skipped: ${error.message}`);
        }
      }

      // 3. Initialize ConsensusMain
      if (deployedContracts.ConsensusMain &&
          deployedContracts.ConsensusMain.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          // Check if already initialized
          if (deployedContracts.ConsensusMain.interface.fragments.some(f => f.name === 'owner')) {
            const owner = await deployedContracts.ConsensusMain.owner();
            if (owner === "0x0000000000000000000000000000000000000000") {
              console.log(`Initializing ConsensusMain...`);
              await deployedContracts.ConsensusMain.initialize();
            }
          } else {
            try {
              await deployedContracts.ConsensusMain.initialize();
            } catch (error) {
              // Likely already initialized, ignore
            }
          }
        } catch (error) {
          console.log(`ConsensusMain initialization skipped: ${error.message}`);
        }
      }

      // 4. Initialize Transactions
      if (deployedContracts.Transactions && deployedContracts.ConsensusMain &&
          deployedContracts.Transactions.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          console.log(`Setting up Transactions...`);
          try {
            await deployedContracts.Transactions.initialize(
              deployedContracts.ConsensusMain.address
            );
          } catch (error) {
            // Might be already initialized, continue
          }
        } catch (error) {
          console.log(`Transactions initialization skipped: ${error.message}`);
        }
      }

      // 5. Initialize Queues
      if (deployedContracts.Queues && deployedContracts.ConsensusMain &&
          deployedContracts.Queues.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          console.log(`Setting up Queues...`);
          try {
            await deployedContracts.Queues.initialize(
              deployedContracts.ConsensusMain.address
            );
          } catch (error) {
            // Might be already initialized, continue
          }
        } catch (error) {
          console.log(`Queues initialization skipped: ${error.message}`);
        }
      }

      // 6. Initialize Messages
      if (deployedContracts.Messages &&
          deployedContracts.Messages.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          console.log(`Setting up Messages...`);
          try {
            await deployedContracts.Messages.initialize();
          } catch (error) {
            // Might be already initialized, continue
          }
        } catch (error) {
          console.log(`Messages initialization skipped: ${error.message}`);
        }
      }

      // 7. Initialize ConsensusData
      if (deployedContracts.ConsensusData && deployedContracts.ConsensusMain &&
          deployedContracts.Transactions && deployedContracts.Queues &&
          deployedContracts.ConsensusData.interface.fragments.some(f => f.name === 'initialize')) {
        try {
          console.log(`Setting up ConsensusData...`);
          try {
            await deployedContracts.ConsensusData.initialize(
              deployedContracts.ConsensusMain.address,
              deployedContracts.Transactions.address,
              deployedContracts.Queues.address
            );
          } catch (error) {
            // Might be already initialized, continue
          }
        } catch (error) {
          console.log(`ConsensusData initialization skipped: ${error.message}`);
        }
      }
    };

    // Set up all external contracts and relationships
    const setupContractRelationships = async () => {
      // 1. Set GhostBlueprint in GhostFactory
      if (deployedContracts.GhostFactory && deployedContracts.GhostBlueprint &&
          deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'setGhostBlueprint')) {
        try {
          console.log(`Setting GhostBlueprint in GhostFactory...`);
          await deployedContracts.GhostFactory.setGhostBlueprint(
            deployedContracts.GhostBlueprint.address
          );
        } catch (error) {
          console.log(`Setting GhostBlueprint skipped: ${error.message}`);
        }
      }

      // 2. Set GenConsensus in GhostFactory
      if (deployedContracts.GhostFactory && deployedContracts.ConsensusMain &&
          deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'setGenConsensus')) {
        try {
          console.log(`Setting GenConsensus in GhostFactory...`);
          await deployedContracts.GhostFactory.setGenConsensus(
            deployedContracts.ConsensusMain.address
          );
        } catch (error) {
          console.log(`Setting GenConsensus in GhostFactory skipped: ${error.message}`);
        }
      }

      // 3. Set GhostManager in GhostFactory
      if (deployedContracts.GhostFactory && deployedContracts.ConsensusMain &&
          deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'setGhostManager')) {
        try {
          console.log(`Setting GhostManager in GhostFactory...`);
          await deployedContracts.GhostFactory.setGhostManager(
            deployedContracts.ConsensusMain.address
          );
        } catch (error) {
          console.log(`Setting GhostManager skipped: ${error.message}`);
        }
      }

      // 4. Set GenConsensus in Messages
      if (deployedContracts.Messages && deployedContracts.ConsensusMain &&
          deployedContracts.Messages.interface.fragments.some(f => f.name === 'setGenConsensus')) {
        try {
          console.log(`Setting GenConsensus in Messages...`);
          await deployedContracts.Messages.setGenConsensus(
            deployedContracts.ConsensusMain.address
          );
        } catch (error) {
          console.log(`Setting GenConsensus in Messages skipped: ${error.message}`);
        }
      }

      // 5. Set GenTransactions in Messages
      if (deployedContracts.Messages && deployedContracts.Transactions &&
          deployedContracts.Messages.interface.fragments.some(f => f.name === 'setGenTransactions')) {
        try {
          console.log(`Setting GenTransactions in Messages...`);
          await deployedContracts.Messages.setGenTransactions(
            deployedContracts.Transactions.address
          );
        } catch (error) {
          console.log(`Setting GenTransactions in Messages skipped: ${error.message}`);
        }
      }

      // 6. Set external contracts in ConsensusMain
      if (deployedContracts.ConsensusMain &&
          deployedContracts.GhostFactory &&
          deployedContracts.ConsensusManager &&
          deployedContracts.Transactions &&
          deployedContracts.Queues &&
          deployedContracts.MockGenStaking &&
          deployedContracts.Messages &&
          deployedContracts.Idleness &&
          deployedContracts.ConsensusMain.interface.fragments.some(f => f.name === 'setExternalContracts')) {
        try {
          console.log(`Setting external contracts in ConsensusMain...`);
          await deployedContracts.ConsensusMain.setExternalContracts(
            deployedContracts.GhostFactory.address,
            deployedContracts.ConsensusManager.address,
            deployedContracts.Transactions.address,
            deployedContracts.Queues.address,
            deployedContracts.MockGenStaking.address,
            deployedContracts.Messages.address,
            deployedContracts.Idleness.address
          );
        } catch (error) {
          console.log(`Setting external contracts in ConsensusMain skipped: ${error.message}`);
        }
      }

      // 7. Set external contracts in Transactions
      if (deployedContracts.Transactions &&
          deployedContracts.ConsensusMain &&
          deployedContracts.MockGenStaking &&
          deployedContracts.Rounds &&
          deployedContracts.Voting &&
          deployedContracts.Idleness &&
          deployedContracts.Utils &&
          deployedContracts.Transactions.interface.fragments.some(f => f.name === 'setExternalContracts')) {
        try {
          console.log(`Setting external contracts in Transactions...`);
          await deployedContracts.Transactions.setExternalContracts(
            deployedContracts.ConsensusMain.address,
            deployedContracts.MockGenStaking.address,
            deployedContracts.Rounds.address,
            deployedContracts.Voting.address,
            deployedContracts.Idleness.address,
            deployedContracts.Utils.address
          );
        } catch (error) {
          console.log(`Setting external contracts in Transactions skipped: ${error.message}`);
        }
      }

      // 8. Add validators to MockGenStaking if needed
      if (deployedContracts.MockGenStaking &&
          deployedContracts.MockGenStaking.interface.fragments.some(f => f.name === 'addValidators')) {
        try {
          // Add the validators as in 001_deploy_fixture
          const validators = [
            signers[1].address, // validator1
            signers[2].address, // validator2
            signers[3].address, // validator3
            signers[4].address, // validator4
            signers[5].address  // validator5
          ];

          console.log(`Adding validators to MockGenStaking...`);
          await deployedContracts.MockGenStaking.addValidators(validators);
        } catch (error) {
          console.log(`Adding validators skipped: ${error.message}`);
        }
      }

      // 9. Deploy beacon proxy if needed
      if (deployedContracts.GhostFactory &&
          deployedContracts.GhostFactory.interface.fragments.some(f => f.name === 'deployNewBeaconProxy')) {
        try {
          console.log(`Deploying new beacon proxy from GhostFactory...`);
          await deployedContracts.GhostFactory.deployNewBeaconProxy();
        } catch (error) {
          console.log(`Beacon proxy deployment skipped: ${error.message}`);
        }
      }
    };

    // Execute the initialization sequence
    await initializeContracts();
    await setupContractRelationships();

    console.log(`Contract configurations restored successfully`);
    return true;
  } catch (error) {
    console.log(`Error restoring fixture configurations: ${error.message}`);
    return false;
  }
}

/**
 * Restaura el estado usando evm_revert, y si no funciona, hace una restauración completa
 * @param {object} snapshotData Datos del snapshot
 */
async function restoreState(snapshotData) {
  const snapshotId = snapshotData.id;
  const originalBlockNumber = snapshotData.blockNumber;
  console.log(`Attempting to restore state from block ${originalBlockNumber} with snapshot ID ${snapshotId}...`);

  try {
    // Método 1: Intentar con evm_revert (esto es lo más rápido y fiable)
    const reverted = await hre.network.provider.send("evm_revert", [snapshotId]);

    if (reverted === true) {
      console.log(`evm_revert successful!`);

      // Tomar inmediatamente un nuevo snapshot para preservar el estado
      const newSnapshotId = await hre.network.provider.send("evm_snapshot");
      console.log(`New snapshot taken with ID: ${newSnapshotId}`);

      // Actualizar el snapshot con el nuevo ID
      snapshotData.id = newSnapshotId;

      const snapshotPath = path.join(__dirname, "../snapshots/latest.json");
      fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));

      // Verify current block matches the original
      const currentHex = await hre.network.provider.send("eth_blockNumber");
      const currentBlock = parseInt(currentHex, 16);

      if (currentBlock !== originalBlockNumber) {
        console.log(`Warning: Current block (${currentBlock}) does not match original block (${originalBlockNumber})`);
        await mineToBlock(originalBlockNumber);
      }

      return true;
    } else {
      console.log(`evm_revert failed, falling back to full restoration...`);
    }
  } catch (error) {
    console.log(`Error with evm_revert: ${error.message}`);
    console.log(`Falling back to full restoration...`);
  }

  // Método 2: Restauración completa (si evm_revert falló)
  return await restoreBlockchainState(snapshotData);
}

/**
 * Restauración completa del estado del blockchain (usado como fallback)
 * @param {object} snapshotData Datos del snapshot
 */
async function restoreBlockchainState(snapshotData) {
  console.log(`Starting full state restoration...`);
  const originalBlockNumber = snapshotData.blockNumber;

  // Create snapshots directory if it doesn't exist
  const snapshotsDir = path.join(__dirname, "../snapshots");
  if (!fs.existsSync(snapshotsDir)) {
    fs.mkdirSync(snapshotsDir, { recursive: true });
  }

  // Make sure deployment files exist for all contracts in snapshot
  const deploymentsDir = path.join(__dirname, "../deployments/genlayer_network");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  // Reset completo del nodo
  await hre.network.provider.send("hardhat_reset");

  // Minar hasta el bloque capturado en el snapshot
  await mineToBlock(originalBlockNumber);

  // Restaurar código y storage de contratos
  for (const [contractName, data] of Object.entries(snapshotData.deployments)) {
    // Verificar si el contrato ya tiene código
    const code = await hre.network.provider.send("eth_getCode", [data.address, "latest"]);

    if (code === "0x") {
      // Restaurar bytecode
      let bytecode = data.runtimeCode || data.deployedBytecode || data.bytecode;
      if (!bytecode) {
        console.log(`No bytecode for ${contractName}, skipping`);
        continue;
      }

      if (!bytecode.startsWith("0x")) {
        bytecode = "0x" + bytecode;
      }

      try {
        console.log(`Restoring code for ${contractName} at ${data.address}`);
        await hre.network.provider.send("hardhat_setCode", [data.address, bytecode]);
      } catch (error) {
        console.log(`Error restoring code for ${contractName}: ${error.message}`);
        continue; // Si no podemos restaurar el código, pasamos al siguiente contrato
      }
    }

    // Restaurar storage
    if (data.storage && Object.keys(data.storage).length > 0) {
      console.log(`Restoring ${Object.keys(data.storage).length} storage slots for ${contractName}`);

      for (const [slot, value] of Object.entries(data.storage)) {
        try {
          await hre.network.provider.send("hardhat_setStorageAt", [data.address, slot, value]);
        } catch (error) {
          console.log(`Error restoring slot ${slot}: ${error.message}`);
        }
      }
    }

    // Registrar en hardhat-deploy
    try {
      await hre.deployments.save(contractName, {
        address: data.address,
        abi: data.abi,
        bytecode: data.bytecode,
        deployedBytecode: data.deployedBytecode
      });
    } catch (error) {
      console.log(`Error registering ${contractName}: ${error.message}`);
    }
  }

  // Verify we're at the correct block
  const finalBlockHex = await hre.network.provider.send("eth_blockNumber");
  const finalBlock = parseInt(finalBlockHex, 16);
  if (finalBlock !== originalBlockNumber) {
    console.log(`Final block (${finalBlock}) does not match original (${originalBlockNumber}), mining to correct block...`);
    await mineToBlock(originalBlockNumber);
  }

  // Restore all contract configurations from deploy_fixture
  await restoreFixtureConfigurations(snapshotData);

  // Tomar un nuevo snapshot del estado restaurado
  const newSnapshotId = await hre.network.provider.send("evm_snapshot");
  console.log(`New snapshot taken with ID: ${newSnapshotId}`);

  // Actualizar el archivo de snapshot con el nuevo ID
  snapshotData.id = newSnapshotId;
  const snapshotPath = path.join(__dirname, "../snapshots/latest.json");
  fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));

  return true;
}

/**
 * Ejecuta pruebas para verificar que los contratos funcionan correctamente
 * @param {object} snapshotData Datos del snapshot
 */
async function verifyContractsWork(snapshotData) {
  if (!snapshotData.deployments.ConsensusMain) {
    console.log(`ConsensusMain not found, skipping verification`);
    return;
  }

  try {
    // Verificar que podemos interactuar con ConsensusMain
    console.log(`Verifying ConsensusMain functionality...`);

    const [signer] = await hre.ethers.getSigners();
    const consensusMain = new hre.ethers.Contract(
      snapshotData.deployments.ConsensusMain.address,
      snapshotData.deployments.ConsensusMain.abi,
      signer
    );

    // Verificar que el contrato responde
    const owner = await consensusMain.owner();

    // Verify GhostFactory functionality if it exists
    if (snapshotData.deployments.GhostFactory) {
      console.log(`Verifying GhostFactory functionality...`);

      const ghostFactory = new hre.ethers.Contract(
        snapshotData.deployments.GhostFactory.address,
        snapshotData.deployments.GhostFactory.abi,
        signer
      );

      try {
        const blueprint = await ghostFactory.ghostBlueprint();
        const zeroAddress = "0x0000000000000000000000000000000000000000";
        if (blueprint === zeroAddress) {
          console.log(`Warning: GhostBlueprint is not set in GhostFactory`);
        }
      } catch (error) {
        console.log(`Error checking GhostFactory blueprint: ${error.message}`);
      }
    }

    console.log(`Contract verification successful`);
  } catch (error) {
    console.log(`Error verifying contracts: ${error.message}`);
  }
}

async function takeNewSnapshot() {
  try {
    console.log(`Taking new snapshot after restoration...`);

    // Instead of calling hre.run("snapshot"), directly execute the snapshot script
    // that we know exists in the project
    const snapshotPath = path.join(__dirname, "./snapshot.js");
    if (fs.existsSync(snapshotPath)) {
      // Use require to execute the script
      require(snapshotPath);
    } else {
      console.log(`Snapshot script not found at ${snapshotPath}`);

      // Fallback: Take a basic snapshot
      const newSnapshotId = await hre.network.provider.send("evm_snapshot");
      console.log(`Basic snapshot taken with ID: ${newSnapshotId}`);
    }
  } catch (error) {
    console.log(`Error taking new snapshot: ${error.message}`);
  }
}

async function main() {
  const snapshotPath = path.join(__dirname, "../snapshots/latest.json");

  if (!fs.existsSync(snapshotPath)) {
    console.log(`No snapshot to restore at ${snapshotPath}`);
    return;
  }

  console.log(`Loading snapshot from ${snapshotPath}...`);
  const snapshotData = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));

  // Save original block number for verification at the end
  const originalBlockNumber = snapshotData.blockNumber;
  console.log(`Original block number: ${originalBlockNumber}`);

  // Restaurar el estado
  await restoreState(snapshotData);

  // Verificar que todo funciona correctamente
  await verifyContractsWork(snapshotData);

  // Verify final block number
  const finalBlockHex = await hre.network.provider.send("eth_blockNumber");
  const finalBlock = parseInt(finalBlockHex, 16);

  if (finalBlock !== originalBlockNumber) {
    console.log(`Warning: Final block (${finalBlock}) does not match original (${originalBlockNumber})`);
    console.log(`Mining to reach the target block...`);
    await mineToBlock(originalBlockNumber);
  }

  console.log(`Restoration process completed at block ${finalBlock}`);

  // Take a new snapshot to ensure we can revert to this state again
  await takeNewSnapshot();
}

// Ejecutar el script
main()
  .then(() => process.exit(0))
  .catch(err => {
    console.error(err);
    process.exit(1);
  });
