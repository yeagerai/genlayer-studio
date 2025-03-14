const fs = require("fs-extra");
const path = require("path");
const { ethers } = require("hardhat");


async function saveDeployment(name, contract, folder = "deployments/localhost") {
  try {
    const address = await contract.getAddress();

    // Try to get bytecode from the chain
    let bytecodeOnChain;
    try {
      bytecodeOnChain = await ethers.provider.getCode(address);
    } catch (bytecodeError) {
      console.warn(`Could not get bytecode for ${name}: ${bytecodeError.message}`);
      bytecodeOnChain = "";
    }

    // Minimal ABI from contract.interface
    const fragments = contract.interface.fragments.map((fragment) => {
      const result = {
        type: fragment.type,
        name: fragment.name,
      };
      if (fragment.inputs) result.inputs = fragment.inputs;
      if (fragment.outputs) result.outputs = fragment.outputs;
      if (fragment.stateMutability) result.stateMutability = fragment.stateMutability;
      return result;
    });

    const deploymentData = {
      address,
      abi: fragments,
      bytecode: bytecodeOnChain,
    };

    await fs.ensureDir(folder);
    const savePath = path.join(folder, `${name}.json`);
    await fs.writeJson(savePath, deploymentData, { spaces: 2 });
    console.log(`Saved deployment for ${name} at ${savePath}`);
  } catch (error) {
    console.error(`Error trying to save ${name}:`, error.message);
  }
}

module.exports = async ({ getNamedAccounts, deployments, ethers }) => {
  const { deploy, execute, log } = deployments;
  const { deployer } = await getNamedAccounts();

  log("Deploying ArrayUtils...");
  const arrayUtilsDeployment = await deploy("ArrayUtils", {
    from: deployer,
    log: true,
  });

  log("Deploying GhostContract...");
  const ghostContractDeployment = await deploy("GhostContract", {
    from: deployer,
    log: true,
  });

  log("Deploying RandomnessUtils...");
  const randomnessUtilsDeployment = await deploy("RandomnessUtils", {
    from: deployer,
    log: true,
  });

  log("Deploying Transactions...");
  const genTransactionsDeployment = await deploy("Transactions", {
    from: deployer,
    libraries: {
      ArrayUtils: arrayUtilsDeployment.address,
    },
    log: true,
  });

  log("Deploying ConsensusManager...");
  const genManagerDeployment = await deploy("ConsensusManager", {
    from: deployer,
    log: true,
  });

  log("Deploying GhostFactory...");
  const ghostFactoryDeployment = await deploy("GhostFactory", {
    from: deployer,
    log: true,
  });

  log("Deploying GhostBlueprint...");
  const ghostBlueprintDeployment = await deploy("GhostBlueprint", {
    from: deployer,
    log: true,
  });

  log("Deploying MockGenStaking...");
  const genStakingDeployment = await deploy("MockGenStaking", {
    from: deployer,
    log: true,
  });

  log("Deploying Queues...");
  const genQueueDeployment = await deploy("Queues", {
    from: deployer,
    log: true,
  });

  log("Deploying Messages...");
  const messagesDeployment = await deploy("Messages", {
    from: deployer,
    log: true,
  });

  log("Deploying FeeManager...");
  const feeManagerDeployment = await deploy("FeeManager", {
    from: deployer,
    log: true,
  });

  log("Deploying Utils...");
  const utilsDeployment = await deploy("Utils", {
    from: deployer,
    log: true,
  });

  log("Deploying Rounds...");
  const roundsDeployment = await deploy("Rounds", {
    from: deployer,
    libraries: {
      ArrayUtils: arrayUtilsDeployment.address,
      RandomnessUtils: randomnessUtilsDeployment.address,
    },
    args: [
      genStakingDeployment.address,
      feeManagerDeployment.address,
      utilsDeployment.address,
    ],
    log: true,
  });

  log("Deploying Voting...");
  const votingDeployment = await deploy("Voting", {
    from: deployer,
    log: true,
  });

  log("Deploying Idleness...");
  const idlenessDeployment = await deploy("Idleness", {
    from: deployer,
    libraries: {
      ArrayUtils: arrayUtilsDeployment.address,
    },
    args: [
      genTransactionsDeployment.address,
      genStakingDeployment.address,
      utilsDeployment.address,
    ],
    log: true,
  });

  log("Deploying ConsensusMain...");
  const consensusMainDeployment = await deploy("ConsensusMain", {
    from: deployer,
    log: true,
  });

  log("Deploying ConsensusData...");
  const consensusDataDeployment = await deploy("ConsensusData", {
    from: deployer,
    log: true,
  });

  // GhostFactory
  if (ghostFactoryDeployment.newlyDeployed) {
    log("Initializing GhostFactory...");
    await execute("GhostFactory", { from: deployer }, "initialize");
  } else {
    log("Skipping GhostFactory.initialize() (already deployed).");
  }

  // GhostBlueprint
  if (ghostBlueprintDeployment.newlyDeployed) {
    log("Initializing GhostBlueprint...");
    await execute("GhostBlueprint", { from: deployer }, "initialize", deployer);
  } else {
    log("Skipping GhostBlueprint.initialize() (already deployed).");
  }

  // setGhostBlueprint & deployNewBeaconProxy
  if (ghostFactoryDeployment.newlyDeployed) {
    log("Setting GhostBlueprint in GhostFactory...");
    try {
      await execute(
        "GhostFactory",
        { from: deployer, gasLimit: 5000000 },
        "setGhostBlueprint",
        ghostBlueprintDeployment.address
      );
      log("GhostBlueprint set successfully");

      log("Deploying new beacon proxy...");
      await execute(
        "GhostFactory",
        { from: deployer, gasLimit: 5000000 },
        "deployNewBeaconProxy"
      );
      log("Beacon proxy deployed successfully");
    } catch (err) {
      log(`Error in GhostFactory setup: ${err.message}`);
    }
  } else {
    log("Skipping GhostFactory blueprint & beacon proxy setup (already deployed).");
  }

  // ConsensusMain
  if (consensusMainDeployment.newlyDeployed) {
    log("Initializing ConsensusMain...");
    await execute("ConsensusMain", { from: deployer }, "initialize");
  } else {
    log("Skipping ConsensusMain.initialize() (already deployed).");
  }

  // Transactions
  if (genTransactionsDeployment.newlyDeployed) {
    log("Initializing Transactions...");
    await execute(
      "Transactions",
      { from: deployer },
      "initialize",
      consensusMainDeployment.address
    );
  } else {
    log("Skipping Transactions.initialize() (already deployed).");
  }

  // Queues
  if (genQueueDeployment.newlyDeployed) {
    log("Initializing Queues...");
    await execute(
      "Queues",
      { from: deployer },
      "initialize",
      consensusMainDeployment.address
    );
  } else {
    log("Skipping Queues.initialize() (already deployed).");
  }

  // Messages
  if (messagesDeployment.newlyDeployed) {
    log("Initializing Messages...");
    await execute("Messages", { from: deployer }, "initialize");
  } else {
    log("Skipping Messages.initialize() (already deployed).");
  }

  // setExternalContracts en ConsensusMain
  if (consensusMainDeployment.newlyDeployed) {
    log("Setting external contracts in ConsensusMain...");
    try {
      await execute(
        "ConsensusMain",
        { from: deployer, gasLimit: 5000000 },
        "setExternalContracts",
        ghostFactoryDeployment.address,
        genManagerDeployment.address,
        genTransactionsDeployment.address,
        genQueueDeployment.address,
        genStakingDeployment.address,
        messagesDeployment.address,
        idlenessDeployment.address
      );
      log("External contracts set in ConsensusMain");
    } catch (err) {
      log(`Error setting external contracts in ConsensusMain: ${err.message}`);
    }
  } else {
    log("Skipping setExternalContracts in ConsensusMain (already deployed).");
  }

  // setExternalContracts en Transactions
  if (genTransactionsDeployment.newlyDeployed) {
    log("Setting external contracts in Transactions...");
    try {
      await execute(
        "Transactions",
        { from: deployer, gasLimit: 5000000 },
        "setExternalContracts",
        consensusMainDeployment.address,
        genStakingDeployment.address,
        roundsDeployment.address,
        votingDeployment.address,
        idlenessDeployment.address,
        utilsDeployment.address
      );
      log("External contracts set in Transactions");
    } catch (err) {
      log(`Error setting external contracts in Transactions: ${err.message}`);
    }
  } else {
    log("Skipping setExternalContracts in Transactions (already deployed).");
  }

  // ConsensusData
  if (consensusDataDeployment.newlyDeployed) {
    log("Initializing ConsensusData...");
    try {
      await execute(
        "ConsensusData",
        { from: deployer, gasLimit: 5000000 },
        "initialize",
        consensusMainDeployment.address,
        genTransactionsDeployment.address,
        genQueueDeployment.address
      );
      log("ConsensusData initialized");
    } catch (err) {
      log(`Error initializing ConsensusData: ${err.message}`);
    }
  } else {
    log("Skipping ConsensusData.initialize() (already deployed).");
  }

  // setGenConsensus & setGhostManager en GhostFactory
  if (ghostFactoryDeployment.newlyDeployed) {
    log("Setting GenConsensus in GhostFactory...");
    try {
      await execute(
        "GhostFactory",
        { from: deployer, gasLimit: 3000000 },
        "setGenConsensus",
        consensusMainDeployment.address
      );
      log("GenConsensus set in GhostFactory");
    } catch (err) {
      log(`Error setting GenConsensus in GhostFactory: ${err.message}`);
    }

    log("Setting GhostManager in GhostFactory...");
    try {
      await execute(
        "GhostFactory",
        { from: deployer, gasLimit: 3000000 },
        "setGhostManager",
        consensusMainDeployment.address
      );
      log("GhostManager set in GhostFactory");
    } catch (err) {
      log(`Error setting GhostManager in GhostFactory: ${err.message}`);
    }
  } else {
    log("Skipping setGenConsensus & setGhostManager in GhostFactory (already deployed).");
  }

  // setGenConsensus, setGenTransactions en Messages
  if (messagesDeployment.newlyDeployed) {
    log("Setting GenConsensus in Messages...");
    try {
      await execute(
        "Messages",
        { from: deployer, gasLimit: 3000000 },
        "setGenConsensus",
        consensusMainDeployment.address
      );
      log("GenConsensus set in Messages");
    } catch (err) {
      log(`Error setting GenConsensus in Messages: ${err.message}`);
    }

    log("Setting GenTransactions in Messages...");
    try {
      await execute(
        "Messages",
        { from: deployer, gasLimit: 3000000 },
        "setGenTransactions",
        genTransactionsDeployment.address
      );
      log("GenTransactions set in Messages");
    } catch (err) {
      log(`Error setting GenTransactions in Messages: ${err.message}`);
    }
  } else {
    log("Skipping setGenConsensus & setGenTransactions in Messages (already deployed).");
  }

  // addValidators en MockGenStaking
  if (genStakingDeployment.newlyDeployed) {
    const signers = await ethers.getSigners();
    const validator1 = signers[1].address;
    const validator2 = signers[2].address;
    const validator3 = signers[3].address;
    const validator4 = signers[4].address;
    const validator5 = signers[5].address;

    log("Adding validators...");
    try {
      await execute(
        "MockGenStaking",
        { from: deployer, gasLimit: 3000000 },
        "addValidators",
        [validator1, validator2, validator3, validator4, validator5]
      );
      log("Validators added successfully");
    } catch (err) {
      log(`Error adding validators: ${err.message}`);
    }
  } else {
    log("Skipping addValidators in MockGenStaking (already deployed).");
  }

  log("All contracts deployed and configured!\n");

  //
  // 3) Guardar manualmente en deployments/localhost
  //
  const contractNames = [
    "ArrayUtils",
    "GhostContract",
    "RandomnessUtils",
    "Transactions",
    "ConsensusManager",
    "GhostFactory",
    "GhostBlueprint",
    "MockGenStaking",
    "Queues",
    "Messages",
    "FeeManager",
    "Utils",
    "Rounds",
    "Voting",
    "Idleness",
    "ConsensusMain",
    "ConsensusData",
  ];

  for (const name of contractNames) {
    try {
      const d = await deployments.get(name);
      const contractInstance = await ethers.getContractAt(name, d.address);
      await saveDeployment(name, contractInstance, "deployments/localhost");
    } catch (err) {
      console.error(`Error saving contract ${name}:`, err.message);
    }
  }

  log("All contracts deployed, executed inits, and saved in deployments/localhost!\n");
};

module.exports.tags = ["All"];
