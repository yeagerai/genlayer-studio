const hre = require("hardhat");
const fs = require("fs-extra");
const path = require("path");

/**
 * Save the deployment of a contract to a file.
 * @param {string} name - The name of the contract.
 * @param {Contract} contract - The contract instance.
 * @param {string} folder - The folder to save the deployment file.
 */
async function saveDeployment(name, contract, folder = "deployments/localhost") {
    const deploymentData = {
        address: await contract.getAddress(),
        abi: JSON.parse(contract.interface.formatJson()),
        bytecode: (await hre.artifacts.readArtifact(name)).bytecode
    };

    await fs.ensureDir(folder);
    const savePath = path.join(folder, `${name}.json`);
    await fs.writeJson(savePath, deploymentData, { spaces: 2 });
}

/**
 * Main function to deploy contracts and save their deployments.
 */
async function main() {
    console.log("\nDeploying contracts with Ignition...");
    const DeployFixture = require("../ignition/modules/DeployFixture");
    const result = await hre.ignition.deploy(DeployFixture);

    try {
        for (const [name, contract] of Object.entries(result)) {
            console.log(`Saving ${name}...`);
            await saveDeployment(name, contract);
        }
    } catch (error) {
        console.error("Error saving deployment:", error);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });