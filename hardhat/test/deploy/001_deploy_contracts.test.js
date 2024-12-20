const { expect } = require("chai");
const { ethers } = require("hardhat");
const { ZeroAddress } = ethers;
const fs = require("fs-extra");
const path = require("path");

describe("Deploy Script", function () {
    let contracts = {};
    let owner, validator1, validator2, validator3;

    const expectedContracts = [
        'GhostContract',
        'ConsensusManager',
        'GhostBlueprint',
        'GhostFactory',
        'MockGenStaking',
        'Queues',
        'Transactions',
        'Messages',
        'ConsensusMain',
        'ConsensusData'
    ];

    before(async function () {
        [owner, validator1, validator2, validator3] = await ethers.getSigners();

        // Execute the deployment using Ignition
        const DeployFixture = require("../../ignition/modules/DeployFixture");
        const result = await hre.ignition.deploy(DeployFixture);

        // Save the references to the contracts
        contracts = result;
    });

    describe("Deployment Files Verification", function() {
        it("should have all contracts in directories", async function() {
            console.log("\n[Test] Verifying contract files in directories...");

            const deployPath = path.join('./deployments/localhost');

            for (const contractName of expectedContracts) {
                // Verify in deployments
                const deployContractPath = path.join(deployPath, `${contractName}.json`);
                expect(
                    await fs.pathExists(deployContractPath),
                    `${contractName} should exist in deployments directory`
                ).to.be.true;


                // Verify that the files are valid and match
                const deployData = JSON.parse(await fs.readFile(deployContractPath, 'utf8'));

                const contractAddress = await contracts[contractName].getAddress();
                expect(deployData.address, `${contractName} should have valid address in deployments`)
                    .to.equal(contractAddress);

                console.log(`[Test] ✓ ${contractName} verified`);
            }
        });
    });

    describe("Deployment Initialization and Configuration Validation", function() {
        console.log("\n[Test] Verifying contract initialization and configuration...");

        it("should get all the contracts addresses", async function() {
            for (const contractName of expectedContracts) {
                expect(
                    await contracts[contractName].getAddress(),
                    `${contractName} should have an address`
                ).to.not.equal(ZeroAddress);
            }
        });

        it("should have initialized GhostFactory properly", async function() {
            const ghostBlueprintAddress = await contracts.GhostFactory.ghostBlueprint();
            expect(ghostBlueprintAddress, "GhostFactory should have been initialized with GhostBlueprint address")
                .to.equal(await contracts.GhostBlueprint.getAddress());
        });

        it("should have initialized ConsensusMain properly", async function() {
            const genManagerAddress = await contracts.ConsensusMain.genManager();
            expect(genManagerAddress, "ConsensusMain should have been initialized with GenManager address")
                .to.equal(await contracts.ConsensusManager.getAddress());
        });

        it("should have initialized Transactions, Queues and Messages with the ConsensusMain address", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();

            expect(
                await contracts.Transactions.genConsensus(),
                "Transactions should have been initialized with ConsensusMain address"
            ).to.equal(consensusMainAddress);

            expect(
                await contracts.Queues.genConsensus(),
                "Queues should have been initialized with ConsensusMain address"
            ).to.equal(consensusMainAddress);

            expect(
                await contracts.Messages.genConsensus(),
                "Messages should have been initialized with ConsensusMain address"
            ).to.equal(consensusMainAddress);
        });

        it("should have initialized ConsensusData properly", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();
            const transactionsAddress = await contracts.Transactions.getAddress();
            const queuesAddress = await contracts.Queues.getAddress();

            expect(
                await contracts.ConsensusData.consensusMain(),
                "ConsensusData should have been initialized with ConsensusMain address"
            ).to.equal(consensusMainAddress);

            expect(
                await contracts.ConsensusData.transactions(),
                "ConsensusData should have been initialized with Transactions address"
            ).to.equal(transactionsAddress);

            expect(
                await contracts.ConsensusData.queues(),
                "ConsensusData should have been initialized with Queues address"
            ).to.equal(queuesAddress);
        });

        it("should have set contract connections for ConsensusMain properly", async function() {
            const ghostFactoryAddress = await contracts.GhostFactory.getAddress();
            const genStakingAddress = await contracts.MockGenStaking.getAddress();
            const genQueueAddress = await contracts.Queues.getAddress();
            const genTransactionsAddress = await contracts.Transactions.getAddress();
            const genMessagesAddress = await contracts.Messages.getAddress();

            expect(
                await contracts.ConsensusMain.ghostFactory(),
                "ConsensusMain should have set GhostFactory address"
            ).to.equal(ghostFactoryAddress);
            expect(
                await contracts.ConsensusMain.genStaking(),
                "ConsensusMain should have set GenStaking address"
            ).to.equal(genStakingAddress);
            expect(
                await contracts.ConsensusMain.genQueue(),
                "ConsensusMain should have set GenQueue address"
            ).to.equal(genQueueAddress);
            expect(
                await contracts.ConsensusMain.genTransactions(),
                "ConsensusMain should have set GenTransactions address"
            ).to.equal(genTransactionsAddress);
            expect(
                await contracts.ConsensusMain.genMessages(),
                "ConsensusMain should have set GenMessages address"
            ).to.equal(genMessagesAddress);
        });

        it("should have configured GhostFactory, Transactions and Messages final settings properly", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();
            const transactionsAddress = await contracts.Transactions.getAddress();

            expect(
                await contracts.GhostFactory.genConsensus(),
                "GhostFactory should have set GenConsensus address"
            ).to.equal(consensusMainAddress);
            expect(
                await contracts.GhostFactory.ghostManager(),
                "GhostFactory should have set GhostManager address"
            ).to.equal(consensusMainAddress);
            expect(
                await contracts.Transactions.genConsensus(),
                "Transactions should have set GenConsensus address"
            ).to.equal(consensusMainAddress);
            expect(
                await contracts.Messages.genConsensus(),
                "Messages should have set GenConsensus address"
            ).to.equal(consensusMainAddress);
            expect(
                await contracts.Messages.genTransactions(),
                "Messages should have set GenTransactions address"
            ).to.equal(transactionsAddress);
        });

        it("should have set Acceptance Timeout in ConsensusMain properly", async function() {
            const acceptanceTimeout = await contracts.ConsensusMain.ACCEPTANCE_TIMEOUT();

            expect(acceptanceTimeout, "Acceptance Timeout should have been set in ConsensusMain")
                .to.equal(0);
        });

        it("should have set up validators in MockGenStaking properly", async function() {
            const validatorCount = await contracts.MockGenStaking.getValidatorCount();
            const validators = [];

            for (let i = 0; i < validatorCount; i++) {
                validators.push(await contracts.MockGenStaking.validators(i));
            }

            expect(validators, "MockGenStaking should have set up validators")
                .to.deep.equal([
                    validator1.address,
                    validator2.address,
                    validator3.address
                ]);
        });

    });
});