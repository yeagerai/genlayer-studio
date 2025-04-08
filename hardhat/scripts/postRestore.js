const hre = require("hardhat");
const { ethers } = hre;

async function main() {
  console.log("🔍 Iniciando validaciones post-restore...");

  const [deployer] = await ethers.getSigners();

  const deployments = await hre.deployments.all();

  const requiredContracts = [
    "ConsensusMain",
    "ConsensusData",
    "ConsensusManager",
    "GhostFactory"
  ];

  for (const name of requiredContracts) {
    if (!deployments[name]) {
      console.error(`❌ ${name} no encontrado en deployments`);
      return;
    }
  }

  const consensusMain = await ethers.getContractAt("ConsensusMain", deployments.ConsensusMain.address);
  const consensusData = await ethers.getContractAt("ConsensusData", deployments.ConsensusData.address);
  const genManager = await ethers.getContractAt("ConsensusManager", deployments.ConsensusManager.address);
  const ghostFactory = await ethers.getContractAt("GhostFactory", deployments.GhostFactory.address);

  // 1. Verificar el owner del GhostFactory
  const factoryOwner = await ghostFactory.owner();
  console.log(`👑 Owner de GhostFactory: ${factoryOwner}`);
  console.log(`👤 Deployer actual (signer): ${deployer.address}`);
  if (factoryOwner.toLowerCase() !== deployer.address.toLowerCase()) {
    console.warn("⚠️ El deployer actual NO es el owner de GhostFactory. Esto puede causar errores.");
  }

  // 2. Verificar que ghostBlueprint esté correctamente seteado
  try {
    const blueprintAddress = await ghostFactory.ghostBlueprint();
    console.log(`📦 ghostBlueprint seteado en GhostFactory: ${blueprintAddress}`);
  } catch (err) {
    console.warn(`⚠️ No se pudo leer ghostBlueprint: ${err.message}`);
  }

  // 3. Probar llamada a addTransaction y parsear el evento
  console.log("🧪 Enviando transacción dummy para probar emisión de eventos...");
  const tx = await consensusMain.addTransaction(
    ethers.ZeroAddress,
    ethers.ZeroAddress,
    5,
    2,
    "0x1234"
  );

  const receipt = await tx.wait();
  const logs = receipt.logs || [];

  let found = false;
  for (const log of logs) {
    try {
      const parsed = consensusMain.interface.parseLog(log);
      if (parsed.name === "NewTransaction") {
        console.log("✅ Evento NewTransaction encontrado.");
        console.log(`🧾 TxID: ${parsed.args[0]}`);
        console.log(`👻 Ghost: ${parsed.args[1]}`);
        console.log(`⚡ Activador: ${parsed.args[2]}`);
        found = true;
        break;
      }
    } catch (e) {
      continue; // Ignore unparseable logs
    }
  }

  if (!found) {
    console.error("❌ No se encontró el evento NewTransaction. Posible error en restore.");
  }

  // 4. Estado del último bloque
  const block = await ethers.provider.getBlockNumber();
  console.log(`📦 Block actual: ${block}`);

  console.log("✅ postRestore.js completado.\n");
}

main()
  .then(() => process.exit(0))
  .catch(err => {
    console.error("❌ Error en postRestore.js:", err);
    process.exit(1);
  });
