const { expect } = require("chai");
const { ethers } = require("hardhat");
const { ZeroAddress } = ethers;
const fs = require("fs-extra");
const path = require("path");

describe("Deploy Script", function () {
    let contracts = {};
    let owner, validator1, validator2, validator3, validator4, validator5;

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
        'ConsensusData',
        'ArrayUtils',
        'RandomnessUtils',
        'FeeManager',
        'Utils',
        'Rounds',
        'Voting',
        'Idleness'
    ];

    before(async function () {
        [owner, validator1, validator2, validator3, validator4, validator5] = await ethers.getSigners();

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
            expect(ghostBlueprintAddress).to.equal(await contracts.GhostBlueprint.getAddress());
        });

        it("should have initialized ConsensusMain properly", async function() {
            const consensusManagerAddress = await contracts.ConsensusManager.getAddress();
            const mainContracts = await contracts.ConsensusMain.contracts();
            expect(mainContracts.genManager).to.equal(consensusManagerAddress);
        });

        it("should have initialized Transactions with all its dependencies", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();
            const contracts_ = await contracts.Transactions.contracts();

            // Añadimos logs para debug
            console.log("Contracts from Transactions:", contracts_);
            console.log("Expected ConsensusMain:", consensusMainAddress);
            console.log("Expected MockGenStaking:", await contracts.MockGenStaking.getAddress());
            console.log("Expected Rounds:", await contracts.Rounds.getAddress());
            console.log("Expected Voting:", await contracts.Voting.getAddress());
            console.log("Expected Idleness:", await contracts.Idleness.getAddress());
            console.log("Expected Utils:", await contracts.Utils.getAddress());

            // Verificamos cada contrato individualmente
            expect(contracts_.genConsensus, "genConsensus mismatch").to.equal(consensusMainAddress);
            expect(contracts_.genStaking, "genStaking mismatch").to.equal(await contracts.MockGenStaking.getAddress());
            expect(contracts_.rounds, "rounds mismatch").to.equal(await contracts.Rounds.getAddress());
            expect(contracts_.voting, "voting mismatch").to.equal(await contracts.Voting.getAddress());
            expect(contracts_.idleness, "idleness mismatch").to.equal(await contracts.Idleness.getAddress());
            expect(contracts_.utils, "utils mismatch").to.equal(await contracts.Utils.getAddress());
        });

        it("should have initialized ConsensusData properly", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();
            const transactionsAddress = await contracts.Transactions.getAddress();
            const queuesAddress = await contracts.Queues.getAddress();

            expect(await contracts.ConsensusData.consensusMain()).to.equal(consensusMainAddress);
            expect(await contracts.ConsensusData.transactions()).to.equal(transactionsAddress);
            expect(await contracts.ConsensusData.queues()).to.equal(queuesAddress);
        });

        it("should have set contract connections for ConsensusMain properly", async function() {
            const mainContracts = await contracts.ConsensusMain.contracts();

            expect(mainContracts.ghostFactory).to.equal(await contracts.GhostFactory.getAddress());
            expect(mainContracts.genStaking).to.equal(await contracts.MockGenStaking.getAddress());
            expect(mainContracts.genQueue).to.equal(await contracts.Queues.getAddress());
            expect(mainContracts.genTransactions).to.equal(await contracts.Transactions.getAddress());
            expect(mainContracts.genMessages).to.equal(await contracts.Messages.getAddress());
            expect(mainContracts.idleness).to.equal(await contracts.Idleness.getAddress());
        });

        it("should have configured GhostFactory and Messages connections properly", async function() {
            const consensusMainAddress = await contracts.ConsensusMain.getAddress();
            const transactionsAddress = await contracts.Transactions.getAddress();

            expect(await contracts.GhostFactory.genConsensus()).to.equal(consensusMainAddress);
            expect(await contracts.GhostFactory.ghostManager()).to.equal(consensusMainAddress);
            expect(await contracts.Messages.genConsensus()).to.equal(consensusMainAddress);
            expect(await contracts.Messages.genTransactions()).to.equal(transactionsAddress);
        });

        it("should have set up validators in MockGenStaking properly", async function() {
            const validatorCount = await contracts.MockGenStaking.getValidatorCount();
            const validators = [];

            for (let i = 0; i < validatorCount; i++) {
                validators.push(await contracts.MockGenStaking.validators(i));
            }

            expect(validators).to.deep.equal([
                validator1.address,
                validator2.address,
                validator3.address,
                validator4.address,
                validator5.address
            ]);
        });

        it("should verify all validators are correctly registered", async function() {
            expect(
                await contracts.MockGenStaking.isValidator(validator1.address),
                "Validator1 should be registered"
            ).to.be.true;

            expect(
                await contracts.MockGenStaking.isValidator(validator2.address),
                "Validator2 should be registered"
            ).to.be.true;

            expect(
                await contracts.MockGenStaking.isValidator(validator3.address),
                "Validator3 should be registered"
            ).to.be.true;

            expect(
                await contracts.MockGenStaking.isValidator(validator4.address),
                "Validator4 should be registered"
            ).to.be.true;

            expect(
                await contracts.MockGenStaking.isValidator(validator5.address),
                "Validator5 should be registered"
            ).to.be.true;
        });
    });
});