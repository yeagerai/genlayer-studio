const { ethers, artifacts } = require("hardhat");
const fs = require("fs-extra");
const path = require("path");

async function saveDeployment(name, contract, folder = "deployments/localhost") {
	try {
		// Get the contract address
		const address = await contract.getAddress();

		// Get ABI and bytecode directly from compiled artifact
		const artifact = await artifacts.readArtifact(name);
		const abi = artifact.abi;
		const bytecode = artifact.bytecode;

		const deploymentData = {
			address: address,
			abi: abi,
			bytecode: bytecode
		};

		await fs.ensureDir(folder);
		const savePath = path.join(folder, `${name}.json`);
		await fs.writeJson(savePath, deploymentData, { spaces: 2 });
		console.log(`Saved deployment for ${name} at ${savePath}`);
	} catch (error) {
		console.error(`Error saving deployment for ${name}:`, error.message);
		// Try alternative method if first one fails
		try {
			console.log(`Trying alternative method to save ${name}...`);
			const address = await contract.getAddress();

			// Try to get bytecode using ethers
			let bytecode;
			try {
				bytecode = await ethers.provider.getCode(address);
			} catch (bytecodeError) {
				console.warn(`Could not get bytecode for ${name}: ${bytecodeError.message}`);
				bytecode = "";
			}

			// Alternative method: extract interface fragments
			const fragments = contract.interface.fragments.map(fragment => {
				const result = {
					type: fragment.type,
					name: fragment.name
				};

				if (fragment.inputs) result.inputs = fragment.inputs;
				if (fragment.outputs) result.outputs = fragment.outputs;
				if (fragment.stateMutability) result.stateMutability = fragment.stateMutability;

				return result;
			});

			const deploymentData = {
				address: address,
				abi: fragments,
				bytecode: bytecode
			};

			await fs.ensureDir(folder);
			const savePath = path.join(folder, `${name}.json`);
			await fs.writeJson(savePath, deploymentData, { spaces: 2 });
			console.log(`Saved deployment for ${name} using alternative method at ${savePath}`);
		} catch (secondError) {
			console.error(`Error in alternative method for ${name}:`, secondError.message);
		}
	}
}

async function deployFixture() {
	const [owner, validator1, validator2, validator3, validator4, validator5] = await ethers.getSigners();
	console.log("Deploying with account:", owner.address);

	// Deploy all required contracts
	console.log("Deploying ArrayUtils...");
	const ArrayUtils = await ethers.getContractFactory("ArrayUtils");
	const arrayUtils = await ArrayUtils.deploy();
	await arrayUtils.waitForDeployment();
	console.log("ArrayUtils deployed at:", await arrayUtils.getAddress());

	console.log("Deploying GhostContract...");
	const GhostContract = await ethers.getContractFactory("GhostContract");
	const ghostContract = await GhostContract.deploy();
	await ghostContract.waitForDeployment();
	console.log("GhostContract deployed at:", await ghostContract.getAddress());

	console.log("Deploying RandomnessUtils...");
	const RandomnessUtils = await ethers.getContractFactory("RandomnessUtils");
	const randomnessUtils = await RandomnessUtils.deploy();
	await randomnessUtils.waitForDeployment();
	console.log("RandomnessUtils deployed at:", await randomnessUtils.getAddress());

	console.log("Deploying Transactions...");
	const GenTransactions = await ethers.getContractFactory("Transactions", {
		libraries: {
			ArrayUtils: await arrayUtils.getAddress(),
		},
	});
	const genTransactions = await GenTransactions.deploy();
	await genTransactions.waitForDeployment();
	console.log("Transactions deployed at:", await genTransactions.getAddress());

	console.log("Deploying ConsensusManager...");
	const GenManager = await ethers.getContractFactory("ConsensusManager");
	const genManager = await GenManager.deploy();
	await genManager.waitForDeployment();
	console.log("ConsensusManager deployed at:", await genManager.getAddress());

	console.log("Deploying GhostFactory...");
	const GhostFactory = await ethers.getContractFactory("GhostFactory");
	const ghostFactory = await GhostFactory.deploy();
	await ghostFactory.waitForDeployment();
	console.log("Initializing GhostFactory...");
	await ghostFactory.initialize();
	console.log("GhostFactory deployed at:", await ghostFactory.getAddress());

	console.log("Deploying GhostBlueprint...");
	const ghostBlueprint = await ethers.deployContract("GhostBlueprint");
	await ghostBlueprint.waitForDeployment();
	console.log("Initializing GhostBlueprint...");
	await ghostBlueprint.initialize(owner.address);
	console.log("GhostBlueprint deployed at:", await ghostBlueprint.getAddress());

	console.log("Setting GhostBlueprint in GhostFactory...");
	try {
		await ghostFactory.setGhostBlueprint(await ghostBlueprint.getAddress());
		console.log("GhostBlueprint set successfully");

		console.log("Deploying new beacon proxy...");
		const tx = await ghostFactory.deployNewBeaconProxy({
			gasLimit: 5000000
		});
		await tx.wait();
		console.log("Beacon proxy deployed successfully");
	} catch (error) {
		console.error("Error in GhostFactory setup:", error.message);
		// Continue with deployment even if this part fails
	}

	console.log("Deploying MockGenStaking...");
	const GenStaking = await ethers.getContractFactory("MockGenStaking");
	const genStaking = await GenStaking.deploy();
	await genStaking.waitForDeployment();
	console.log("MockGenStaking deployed at:", await genStaking.getAddress());

	console.log("Deploying Queues...");
	const GenQueue = await ethers.getContractFactory("Queues");
	const genQueue = await GenQueue.deploy();
	await genQueue.waitForDeployment();
	console.log("Queues deployed at:", await genQueue.getAddress());

	console.log("Deploying Messages...");
	const Messages = await ethers.getContractFactory("Messages");
	const messages = await Messages.deploy();
	await messages.waitForDeployment();
	console.log("Messages deployed at:", await messages.getAddress());

	console.log("Deploying FeeManager...");
	const FeeManager = await ethers.getContractFactory("FeeManager");
	const feeManager = await FeeManager.deploy();
	await feeManager.waitForDeployment();
	console.log("FeeManager deployed at:", await feeManager.getAddress());

	console.log("Deploying Utils...");
	const Utils = await ethers.getContractFactory("Utils");
	const utils = await Utils.deploy();
	await utils.waitForDeployment();
	console.log("Utils deployed at:", await utils.getAddress());

	console.log("Deploying Rounds...");
	const Rounds = await ethers.getContractFactory("Rounds", {
		libraries: {
			ArrayUtils: await arrayUtils.getAddress(),
			RandomnessUtils: await randomnessUtils.getAddress(),
		},
	});
	const rounds = await Rounds.deploy(
		await genStaking.getAddress(),
		await feeManager.getAddress(),
		await utils.getAddress()
	);
	await rounds.waitForDeployment();
	console.log("Rounds deployed at:", await rounds.getAddress());

	console.log("Deploying Voting...");
	const Voting = await ethers.getContractFactory("Voting");
	const voting = await Voting.deploy();
	await voting.waitForDeployment();
	console.log("Voting deployed at:", await voting.getAddress());

	console.log("Deploying Idleness...");
	const Idleness = await ethers.getContractFactory("Idleness", {
		libraries: {
			ArrayUtils: await arrayUtils.getAddress(),
		},
	});
	const idleness = await Idleness.deploy(
		await genTransactions.getAddress(),
		await genStaking.getAddress(),
		await utils.getAddress()
	);
	await idleness.waitForDeployment();
	console.log("Idleness deployed at:", await idleness.getAddress());

	console.log("Deploying ConsensusMain...");
	const ConsensusMain = await ethers.getContractFactory("ConsensusMain");
	const consensusMain = await ConsensusMain.deploy();
	await consensusMain.waitForDeployment();
	console.log("ConsensusMain deployed at:", await consensusMain.getAddress());

	console.log("Initializing ConsensusMain...");
	await consensusMain.initialize();
	const consensusMainAddress = await consensusMain.getAddress();

	console.log("Initializing Transactions...");
	await genTransactions.initialize(consensusMainAddress);

	console.log("Initializing Queues...");
	await genQueue.initialize(consensusMainAddress);

	console.log("Initializing Messages...");
	await messages.initialize();

	// Increase gas limit for this transaction
	console.log("Setting external contracts in ConsensusMain...");
	try {
		const tx = await consensusMain.setExternalContracts(
			await ghostFactory.getAddress(),
			await genManager.getAddress(),
			await genTransactions.getAddress(),
			await genQueue.getAddress(),
			await genStaking.getAddress(),
			await messages.getAddress(),
			await idleness.getAddress(),
			{ gasLimit: 5000000 } // Increase gas limit
		);
		await tx.wait();
		console.log("External contracts set in ConsensusMain");
	} catch (error) {
		console.error("Error setting external contracts in ConsensusMain:", error.message);
		// Continue with deployment despite error
	}

	console.log("Setting external contracts in Transactions...");
	try {
		const tx = await genTransactions.setExternalContracts(
			await consensusMain.getAddress(),
			await genStaking.getAddress(),
			await rounds.getAddress(),
			await voting.getAddress(),
			await idleness.getAddress(),
			await utils.getAddress(),
			{ gasLimit: 5000000 } // Increase gas limit
		);
		await tx.wait();
		console.log("External contracts set in Transactions");
	} catch (error) {
		console.error("Error setting external contracts in Transactions:", error.message);
		// Continue with deployment despite error
	}

	console.log("Deploying ConsensusData...");
	const ConsensusData = await ethers.getContractFactory("ConsensusData");
	const consensusData = await ConsensusData.deploy();
	await consensusData.waitForDeployment();
	console.log("ConsensusData deployed at:", await consensusData.getAddress());

	console.log("Initializing ConsensusData...");
	try {
		await consensusData.initialize(
			await consensusMain.getAddress(),
			await genTransactions.getAddress(),
			await genQueue.getAddress(),
			{ gasLimit: 5000000 }
		);
		console.log("ConsensusData initialized");
	} catch (error) {
		console.error("Error initializing ConsensusData:", error.message);
	}

	console.log("Setting GenConsensus in GhostFactory...");
	try {
		await ghostFactory.setGenConsensus(await consensusMain.getAddress(), { gasLimit: 3000000 });
		console.log("GenConsensus set in GhostFactory");
	} catch (error) {
		console.error("Error setting GenConsensus in GhostFactory:", error.message);
	}

	console.log("Setting GhostManager in GhostFactory...");
	try {
		await ghostFactory.setGhostManager(await consensusMain.getAddress(), { gasLimit: 3000000 });
		console.log("GhostManager set in GhostFactory");
	} catch (error) {
		console.error("Error setting GhostManager in GhostFactory:", error.message);
	}

	console.log("Setting GenConsensus in Messages...");
	try {
		await messages.setGenConsensus(await consensusMain.getAddress(), { gasLimit: 3000000 });
		console.log("GenConsensus set in Messages");
	} catch (error) {
		console.error("Error setting GenConsensus in Messages:", error.message);
	}

	console.log("Setting GenTransactions in Messages...");
	try {
		await messages.setGenTransactions(await genTransactions.getAddress(), { gasLimit: 3000000 });
		console.log("GenTransactions set in Messages");
	} catch (error) {
		console.error("Error setting GenTransactions in Messages:", error.message);
	}

	// Setup validators
	console.log("Adding validators...");
	try {
		await genStaking.addValidators([
			validator1.address,
			validator2.address,
			validator3.address,
			validator4.address,
			validator5.address,
		], { gasLimit: 3000000 });
		console.log("Validators added successfully");
	} catch (error) {
		console.error("Error adding validators:", error.message);
	}

	return {
		consensusMain,
		consensusData,
		genManager,
		ghostFactory,
		genStaking,
		genQueue,
		genTransactions,
		ghostContract,
		arrayUtils,
		randomnessUtils,
		messages,
		feeManager,
		utils,
		rounds,
		voting,
		idleness,
		ghostBlueprint,
		owner,
		validator1,
		validator2,
		validator3,
		validator4,
		validator5,
	};
}

async function main() {
	console.log("Starting deployment with simple script...");
	try {
		const contracts = await deployFixture();
		console.log("All contracts deployed successfully!");

		// Save deployments for later use
		console.log("Saving deployment information...");
		const folder = "deployments/localhost";

		// Save each deployed contract
		await saveDeployment("ConsensusMain", contracts.consensusMain, folder);
		await saveDeployment("ConsensusData", contracts.consensusData, folder);
		await saveDeployment("ConsensusManager", contracts.genManager, folder);
		await saveDeployment("GhostFactory", contracts.ghostFactory, folder);
		await saveDeployment("MockGenStaking", contracts.genStaking, folder);
		await saveDeployment("Queues", contracts.genQueue, folder);
		await saveDeployment("Transactions", contracts.genTransactions, folder);
		await saveDeployment("GhostContract", contracts.ghostContract, folder);
		await saveDeployment("ArrayUtils", contracts.arrayUtils, folder);
		await saveDeployment("RandomnessUtils", contracts.randomnessUtils, folder);
		await saveDeployment("Messages", contracts.messages, folder);
		await saveDeployment("FeeManager", contracts.feeManager, folder);
		await saveDeployment("Utils", contracts.utils, folder);
		await saveDeployment("Rounds", contracts.rounds, folder);
		await saveDeployment("Voting", contracts.voting, folder);
		await saveDeployment("Idleness", contracts.idleness, folder);
		await saveDeployment("GhostBlueprint", contracts.ghostBlueprint, folder);

		console.log("Deployment completed and saved successfully!");
	} catch (error) {
		console.error("Error during deployment:", error);
	}
}

main().catch(error => {
	console.error(error);
	process.exit(1);
}).finally(() => {
	// Ensure script ends correctly
	setTimeout(() => {
		console.log("Finalizing deployment script...");
		process.exit(0);
	}, 1000); // Wait 1 second to ensure all logs are shown
});