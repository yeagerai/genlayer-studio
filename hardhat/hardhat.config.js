require("@nomicfoundation/hardhat-toolbox");
require("@nomicfoundation/hardhat-ignition-ethers");

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      viaIR: true
    }
  },
  networks: {
    hardhat: {
      mining: {
        auto: true,
        interval: 0
      },
      chainId: 31337,
      gasPrice: 0,
      initialBaseFeePerGas: 0,
      blockGasLimit: 30000000,
      ignition: {
        blockPollingInterval: 1_000,
        timeBeforeBumpingFees: 3 * 60 * 1_000,
        maxFeeBumps: 4,
        requiredConfirmations: 5,
        disableFeeBumping: false,
        deploymentDir: "deployments/localhost",
      },
    },

  }
};