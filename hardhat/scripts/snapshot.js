const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// Función para obtener el balance de una cuenta
async function getAccountBalance(address) {
  const balance = await hre.network.provider.send("eth_getBalance", [address, "latest"]);
  return parseInt(balance, 16);
}

/**
 * Obtiene el storage de un contrato iterando slot por slot hasta un máximo.
 * @param {string} address Dirección del contrato.
 * @param {number} maxSlots Máximo número de slots a leer.
 * @returns {object} Objeto con los slots y sus valores.
 */
async function getContractStorage(address, maxSlots = 50) {
  console.log(`[${new Date().toISOString()}] Leyendo storage para ${address} (hasta ${maxSlots} slots)...`);
  const storage = {};

  // Leemos solo los primeros N slots, uno por uno
  for (let i = 0; i < maxSlots; i++) {
    try {
      const slotHex = "0x" + i.toString(16).padStart(64, "0");
      // Usamos eth_getStorageAt correctamente con el bloque "latest"
      const value = await hre.network.provider.send("eth_getStorageAt", [address, slotHex, "latest"]);

      // Solo guardar valores no cero para ahorrar espacio
      if (value && value !== "0x0000000000000000000000000000000000000000000000000000000000000000") {
        storage[slotHex] = value;
      }
    } catch (error) {
      console.error(`[${new Date().toISOString()}] Error leyendo slot ${i} para ${address}: ${error.message}`);
    }
  }

  console.log(`[${new Date().toISOString()}] Capturados ${Object.keys(storage).length} slots no-cero para ${address}`);
  return storage;
}

/**
 * Captura específicamente el mapping ghostContracts de ConsensusMain
 * @param {string} consensusMainAddress Dirección del contrato ConsensusMain
 * @param {Array} ghostAddresses Array de direcciones de ghost contracts
 * @returns {object} Objeto con los slots de storage del mapping
 */
async function captureGhostContractsMapping(consensusMainAddress, ghostAddresses) {
  console.log(`[${new Date().toISOString()}] Capturando mapping ghostContracts para ${ghostAddresses.length} ghosts...`);
  const storage = {};

  // El slot del mapping ghostContracts es el 1 (según el código del contrato)
  const mappingSlot = 1;

  for (const ghostAddress of ghostAddresses) {
    try {
      // Calcular slot específico para este ghost en el mapping
      // keccak256(abi.encodePacked(ghostAddress, mappingSlot))
      const ethers = hre.ethers;
      const paddedAddress = ethers.utils.hexZeroPad(ghostAddress, 32);
      const paddedSlot = ethers.utils.hexZeroPad(ethers.BigNumber.from(mappingSlot).toHexString(), 32);
      const encodedData = ethers.utils.concat([paddedAddress, paddedSlot]);
      const slotKey = ethers.utils.keccak256(encodedData);

      // Obtener el valor en este slot
      const value = await hre.network.provider.send("eth_getStorageAt", [
        consensusMainAddress,
        slotKey,
        "latest"
      ]);

      // Solo guardar si es true (1)
      if (value && value !== "0x0000000000000000000000000000000000000000000000000000000000000000") {
        storage[slotKey] = value;
        console.log(`[${new Date().toISOString()}] Ghost ${ghostAddress} registrado, valor: ${value}`);
      }
    } catch (error) {
      console.error(`[${new Date().toISOString()}] Error capturando ghost ${ghostAddress}: ${error.message}`);
    }
  }

  return storage;
}

async function main() {
  console.log(`[${new Date().toISOString()}] Iniciando proceso de snapshot...`);
  await new Promise(resolve => setTimeout(resolve, 1000));

  const blockNumber = await hre.network.provider.send("eth_blockNumber");
  const blockNumberDec = parseInt(blockNumber, 16);
  const latestBlock = await hre.network.provider.send("eth_getBlockByNumber", ["latest", true]);
  const accounts = await hre.network.provider.send("eth_accounts");
  const chainId = await hre.network.provider.send("eth_chainId");
  const gasPrice = await hre.network.provider.send("eth_gasPrice");

  const snapshotId = await hre.network.provider.send("evm_snapshot");
  console.log(`[${new Date().toISOString()}] Snapshot tomada con ID: ${snapshotId}`);

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const deploymentDir = path.join(__dirname, "../deployments/genlayer_network");
  const deploymentFiles = fs.readdirSync(deploymentDir).filter(file => file.endsWith(".json"));

  // Fase 1: Recolectar información básica de todos los contratos
  const deployments = {};
  let ghostAddresses = [];

  for (const file of deploymentFiles) {
    const contractName = file.replace(".json", "");
    const deploymentPath = path.join(deploymentDir, file);
    const deploymentData = JSON.parse(fs.readFileSync(deploymentPath, "utf8"));
    const runtimeCode = await hre.network.provider.send("eth_getCode", [deploymentData.address, "latest"]);
    if (runtimeCode === "0x") continue;

    deployments[contractName] = {
      address: deploymentData.address,
      abi: deploymentData.abi,
      bytecode: deploymentData.bytecode,
      deployedBytecode: deploymentData.deployedBytecode,
      runtimeCode
    };

    // Si es GhostFactory, intentamos obtener los ghost contracts
    if (contractName === "GhostFactory" || contractName === "ghostFactory") {
      try {
        console.log(`[${new Date().toISOString()}] Intentando obtener ghosts desde ${contractName}...`);
        const ghostFactory = new hre.ethers.Contract(
          deploymentData.address,
          deploymentData.abi,
          hre.ethers.provider
        );

        // Intentar diferentes métodos para obtener los ghosts
        if (ghostFactory.interface.hasFunction("getGhosts")) {
          ghostAddresses = await ghostFactory.getGhosts();
          console.log(`[${new Date().toISOString()}] Recuperados ${ghostAddresses.length} ghosts usando getGhosts()`);
        } else if (ghostFactory.interface.hasFunction("getAllGhosts")) {
          ghostAddresses = await ghostFactory.getAllGhosts();
          console.log(`[${new Date().toISOString()}] Recuperados ${ghostAddresses.length} ghosts usando getAllGhosts()`);
        } else if (ghostFactory.interface.hasFunction("latestGhost")) {
          const latestGhost = await ghostFactory.latestGhost();
          if (latestGhost && latestGhost !== "0x0000000000000000000000000000000000000000") {
            ghostAddresses = [latestGhost];
            console.log(`[${new Date().toISOString()}] Recuperado último ghost: ${latestGhost}`);
          }
        }
      } catch (error) {
        console.error(`[${new Date().toISOString()}] Error obteniendo ghosts: ${error.message}`);
      }
    }
  }

  // Si no encontramos ghost contracts, buscarlos en eventos de ConsensusMain
  if (ghostAddresses.length === 0 && deployments.ConsensusMain) {
    try {
      console.log(`[${new Date().toISOString()}] Buscando ghosts en eventos de ConsensusMain...`);
      const consensusMain = new hre.ethers.Contract(
        deployments.ConsensusMain.address,
        deployments.ConsensusMain.abi,
        hre.ethers.provider
      );

      const filter = consensusMain.filters.NewTransaction();
      const events = await consensusMain.queryFilter(filter);
      const recipientSet = new Set();

      for (const event of events) {
        if (event.args && event.args.recipient && event.args.recipient !== "0x0000000000000000000000000000000000000000") {
          recipientSet.add(event.args.recipient);
        }
      }

      ghostAddresses = [...recipientSet];
      console.log(`[${new Date().toISOString()}] Encontrados ${ghostAddresses.length} ghosts en eventos`);
    } catch (error) {
      console.error(`[${new Date().toISOString()}] Error buscando ghosts en eventos: ${error.message}`);
    }
  }

  // Fase 2: Capturar storage para los contratos clave
  // Para ConsensusMain, capturamos tanto los primeros slots como el mapping de ghostContracts
  if (deployments.ConsensusMain) {
    console.log(`[${new Date().toISOString()}] Capturando storage básico para ConsensusMain...`);
    const baseStorage = await getContractStorage(deployments.ConsensusMain.address, 10);

    // Si tenemos ghost contracts, capturar también sus slots en el mapping
    let ghostStorage = {};
    if (ghostAddresses.length > 0) {
      ghostStorage = await captureGhostContractsMapping(
        deployments.ConsensusMain.address,
        ghostAddresses
      );
    }

    // Combinar ambos storages
    deployments.ConsensusMain.storage = { ...baseStorage, ...ghostStorage };
    console.log(`[${new Date().toISOString()}] Total slots capturados para ConsensusMain: ${Object.keys(deployments.ConsensusMain.storage).length}`);
  }

  // Capturar storage básico para otros contratos clave
  const keyContracts = ["GhostFactory", "ConsensusManager", "Transactions", "Queues"];
  for (const contractName of keyContracts) {
    if (deployments[contractName]) {
      console.log(`[${new Date().toISOString()}] Capturando storage básico para ${contractName}...`);
      deployments[contractName].storage = await getContractStorage(deployments[contractName].address, 10);
    }
  }

  // Capturar balances y nonces
  const accountBalances = {};
  const accountNonces = {};
  for (const account of accounts) {
    accountBalances[account] = await getAccountBalance(account);
    const nonce = await hre.network.provider.send("eth_getTransactionCount", [account, "latest"]);
    accountNonces[account] = parseInt(nonce, 16);
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
    deployments
  };

  const snapshotsDir = path.join(__dirname, "../snapshots");
  if (!fs.existsSync(snapshotsDir)) fs.mkdirSync(snapshotsDir, { recursive: true });

  const snapshotPath = path.join(snapshotsDir, `snapshot-${timestamp}.json`);
  fs.writeFileSync(snapshotPath, JSON.stringify(snapshotData, null, 2));
  fs.writeFileSync(
    path.join(snapshotsDir, "latest.json"),
    JSON.stringify({ ...snapshotData, file: `snapshot-${timestamp}.json` }, null, 2)
  );
  console.log(`[${new Date().toISOString()}] Snapshot guardada en bloque ${blockNumberDec}`);
}

main()
  .then(() => process.exit(0))
  .catch(e => {
    console.error(e);
    process.exit(1);
  });
