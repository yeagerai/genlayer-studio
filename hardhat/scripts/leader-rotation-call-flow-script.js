const hre = require("hardhat");
const { ethers } = hre;

//
// ================ Auxiliares ================
//

async function generateSignature(signer, currentSeed) {
  const seedBytes = ethers.zeroPadValue(ethers.toBeHex(currentSeed), 32);
  return await signer.signMessage(ethers.getBytes(seedBytes));
}

function findSignerByAddress(validators, address) {
  const validator = validators.find(
    (v) => v.address.toLowerCase() === address.toLowerCase()
  );
  if (!validator) {
    throw new Error(`No validator found for address ${address}`);
  }
  return validator;
}

/**
 * Realiza el flujo:
 *   1) activateTransaction
 *   2) proposeReceipt
 *   3) commitVote (todos)
 *   4) revealVote (todos)
 *   5) (opcional) finalizeTransaction si mayoría es Agree
 *
 * @param {Array<number>} votes Array con un voto por cada validador (ej: [2,2,2,1,1])
 *                              donde 1=Agree,2=Disagree.
 */
async function runConsensusRound(
  consensusMain,
  genManager,
  txId,
  ghostAddress,
  activator,
  vrfProofActivate,
  allValidators,
  messages,
  votes
) {
  // 1) Activate
  const activateTx = await consensusMain
    .connect(activator)
    .activateTransaction(txId, vrfProofActivate);
  const activationReceipt = await activateTx.wait();
  const activationEvent = activationReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "TransactionActivated"
  );
  if (!activationEvent) {
    // Podría significar que la tx ya estaba en "Proposing" (si no se regresa a Pending)
    throw new Error("TransactionActivated event not found");
  }
  const activationParsedLog = consensusMain.interface.parseLog(activationEvent);

  // Extraemos líder y validadores (normalmente 5 en tu implementación)
  const leaderAddr = activationParsedLog.args[1];
  const leader = findSignerByAddress(allValidators, leaderAddr);

  const valAddrsForTx = activationParsedLog.args[2];
  const validatorsForTx = valAddrsForTx.map((addr) => findSignerByAddress(allValidators, addr));
  console.log(">> Round validators assigned by contract:", validatorsForTx.map((v) => v.address));

  // 2) Propose
  const currentSeed = await genManager.recipientRandomSeed(ghostAddress);
  const vrfProofPropose = await generateSignature(leader, BigInt(currentSeed));
  await consensusMain.connect(leader).proposeReceipt(txId, "0x123456", messages, vrfProofPropose);

  // 3) Commit (todos)
  // Asegúrate de usar un array `nonces` de la misma longitud
  // que la cantidad de validadores en la ronda
  const nonces = [111, 222, 333, 444, 555]; // 5 nonces
  for (let i = 0; i < validatorsForTx.length; i++) {
    const voteType = votes[i]; // p.ej, 1=Agree, 2=Disagree
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [validatorsForTx[i].address, voteType, nonces[i]]
    );
    await consensusMain.connect(validatorsForTx[i]).commitVote(txId, voteHash);
  }

  // 4) Reveal (todos)
  // Tras el último reveal se decide si se rota líder, se pasa a "Accepted", etc.
  let receipt;
  for (let i = 0; i < validatorsForTx.length; i++) {
    const voteType = votes[i];
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [validatorsForTx[i].address, voteType, nonces[i]]
    );
    const revealTx = await consensusMain
      .connect(validatorsForTx[i])
      .revealVote(txId, voteHash, voteType, nonces[i]);
    // Esperar a que minen
    receipt = await revealTx.wait();
  }

  return [receipt, leader, validatorsForTx];
}

//
// ================ MAIN SCRIPT ================
//

async function main() {
  console.log("\n=== Iniciando flow de despliegue de Ghost + rotación de líder ===\n");

  // 1. Obtener signers
  const [
    owner,
    validator1,
    validator2,
    validator3,
    validator4,
    validator5,
  ] = await hre.ethers.getSigners();
  const validators = [validator1, validator2, validator3, validator4, validator5];
  console.log("Validators addresses:", validators.map((v) => v.address));

  // 2. Instanciamos los contratos desde /deployments/localhost
  const consensusMainAddress = require("../deployments/localhost/ConsensusMain.json").address;
  const consensusMain = await hre.ethers.getContractAt("ConsensusMain", consensusMainAddress);

  const genManagerAddress = require("../deployments/localhost/ConsensusManager.json").address;
  const genManager = await hre.ethers.getContractAt("ConsensusManager", genManagerAddress);

  const genTransactionsAddress = require("../deployments/localhost/Transactions.json").address;
  const genTransactions = await hre.ethers.getContractAt("Transactions", genTransactionsAddress);

  const consensusDataAddress = require("../deployments/localhost/ConsensusData.json").address;
  const consensusData = await hre.ethers.getContractAt("ConsensusData", consensusDataAddress);

  // 3. Deploy de un token dummy
  console.log("\nDeploying test ERC20 (BasicERC20)...");
  const BasicERC20 = await ethers.getContractFactory("BasicERC20");
  const token = await BasicERC20.deploy("Test Token", "TEST", owner.address);
  await token.mint(owner.address, ethers.parseEther("1000"));
  console.log("- ERC20 token address:", token.target);

  // 4. Crear transacción para desplegar ghost
  console.log("\nCreating transaction to deploy Ghost contract...");
  const numVoters = 3; // se ignora en tu code, pero lo pasamos igual
  const maxRotations = 2;

  const deployTx = await consensusMain.addTransaction(
    ethers.ZeroAddress,
    ethers.ZeroAddress,
    numVoters,
    maxRotations,
    "0x1234" // initCode
  );
  const deployReceipt = await deployTx.wait();
  const deployEvent = deployReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction"
  );
  if (!deployEvent) throw new Error("NewTransaction event not found");

  const deployParsedLog = consensusMain.interface.parseLog(deployEvent);
  const deployTxId = deployParsedLog.args[0];
  const ghostAddress = deployParsedLog.args[1];
  const activatorAddress = deployParsedLog.args[2];

  console.log("- DeployTxID:", deployTxId);
  console.log("- GhostAddress:", ghostAddress);
  console.log("- Activator Address:", activatorAddress);

  // 5. Activator y VRF
  const deployActivator = findSignerByAddress(validators, activatorAddress);
  let currentSeed = await genManager.recipientRandomSeed(ghostAddress);
  let vrfProofActivate = await generateSignature(deployActivator, BigInt(currentSeed));

  // 6. 1.ª ronda de consensus => todos "Agree"
  console.log("\nCompleting consensus for ghost deployment...");
  const votePatternAllAgree = [1,1,1,1,1]; // 5 validators => all "Agree"
  await runConsensusRound(
    consensusMain,
    genManager,
    deployTxId,
    ghostAddress,
    deployActivator,
    vrfProofActivate,
    validators,
    [], // no messages
    votePatternAllAgree
  );

  // Finalizamos la transacción (porque todos “Agree” => Accepted => se puede finalizar).
  let finalizeTx = await consensusMain.finalizeTransaction(deployTxId);
  await finalizeTx.wait();

  // 7. Fund ghost
  console.log("\nFunding ghost contract...");
  await token.transfer(ghostAddress, ethers.parseEther("100"));

  // 8. Crear transacción de transferencia desde ghost
  const GhostBlueprint = await ethers.getContractFactory("GhostBlueprint");
  const ghost = GhostBlueprint.attach(ghostAddress);

  const transferAmount = ethers.parseEther("50");
  const recipient = owner.address;
  const transferData = token.interface.encodeFunctionData("transfer", [recipient, transferAmount]);

  console.log("\nCreating transfer transaction through ghost...");
  const ghostTx = await ghost.addTransaction(numVoters, maxRotations, transferData);
  const ghostReceipt = await ghostTx.wait();
  const ghostEvent = ghostReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction"
  );
  const ghostParsedLog = consensusMain.interface.parseLog(ghostEvent);
  const ghostTxId = ghostParsedLog.args[0];
  const ghostActivatorAddr = ghostParsedLog.args[2];
  const ghostActivator = findSignerByAddress(validators, ghostActivatorAddr);

  // Mensaje a emitir onAcceptance
  const abiCoder = new ethers.AbiCoder();
  const messageData = abiCoder.encode(["address", "bytes"], [token.target, transferData]);
  const message = {
    messageType: 0, // External
    recipient: ghostAddress,
    value: 0,
    data: messageData,
    onAcceptance: true,
  };

  // 9. Ronda con "Disagree" MAYORITARIO (no unánime).
  // => 3 votan 2 (Disagree), 2 votan 1 (Agree) => "MajorityDisagree"
  const votePatternMajorityDisagree = [2,2,2,1,1];
  currentSeed = await genManager.recipientRandomSeed(ghostAddress);
  vrfProofActivate = await generateSignature(ghostActivator, BigInt(currentSeed));

  console.log("\nCompleting consensus with majority Disagree votes...");
  let [receipt, oldLeader] = await runConsensusRound(
    consensusMain,
    genManager,
    ghostTxId,
    ghostAddress,
    ghostActivator,
    vrfProofActivate,
    validators,
    [message],
    votePatternMajorityDisagree
  );

  // Tras la última revelación, si hay "MajorityDisagree", el contrato hace 1 rotación
  // y deja la transacción en estado `Proposing` (o `Undetermined` si no más rotaciones).
  // Chequeamos el evento de rotación:
  let rotationEvent = receipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "TransactionLeaderRotated"
  );
  if (!rotationEvent) {
    throw new Error("TransactionLeaderRotated event not found (did it Disagree?).");
  }
  let leaderRotatedParsedLog = consensusMain.interface.parseLog(rotationEvent);
  let newLeaderAddr = leaderRotatedParsedLog.args[1];
  let newLeader = findSignerByAddress(validators, newLeaderAddr);

  console.log("\nLeader rotation occurred:");
  console.log("- Old leader:", oldLeader.address);
  console.log("- New leader:", newLeader.address);

  // 10. En este punto, el round se "reinicia" con nuevo líder y validadores.
  // => Hacemos propose de nuevo.
  // => PERO tu contrato ya lo hace AUTOMÁTICAMENTE tras la rotación en reveal
  //    (ver si necesita .activateTransaction? A veces re-entra en "Pending"?).
  //
  //   En tu code, la transacción pasa a "Proposing" con nuevo líder,
  //   pero NO se hace proposeReceipt si no lo llamas.
  //   Sin embargo, el test simplifica llamando a `proposeReceipt` manualmente:
  //

  console.log("\nNew leader proposing new receipt...");
  const currentSeed2 = await genManager.recipientRandomSeed(ghostAddress);
  const vrfProofPropose2 = await generateSignature(newLeader, BigInt(currentSeed2));

  // Esta proposeReceipt la llamas SÓLO si tu contract está en estado "Proposing".
  // Sino necesitarías volver a "activateTransaction". Depende la lógica interna.
  await consensusMain
    .connect(newLeader)
    .proposeReceipt(ghostTxId, "0x4567", [message], vrfProofPropose2);

  // 11. Commit + reveal con "Agree" total
  const votePatternAllAgreeAgain = [1,1,1,1,1];
  // Para ello, el round actual ya se habrá registrado en `genTransactions`,
  // con sus validadores. Tomamos esos validadores:
  const txValidators = await genTransactions.getValidatorsForLastRound(ghostTxId);
  const voters = txValidators.map((addr) => findSignerByAddress(validators, addr));
  console.log(">> Round validators (new rotation):", voters.map((v) => v.address));

  // commit
  const nonces2 = [999, 1000, 1001, 1002, 1003];
  for (let i = 0; i < voters.length; i++) {
    const vtype = votePatternAllAgreeAgain[i];
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [voters[i].address, vtype, nonces2[i]]
    );
    await consensusMain.connect(voters[i]).commitVote(ghostTxId, voteHash);
  }

  // reveal
  let lastRevealReceipt;
  for (let i = 0; i < voters.length; i++) {
    const vtype = votePatternAllAgreeAgain[i];
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [voters[i].address, vtype, nonces2[i]]
    );
    const rvTx = await consensusMain
      .connect(voters[i])
      .revealVote(ghostTxId, voteHash, vtype, nonces2[i]);
    lastRevealReceipt = await rvTx.wait();
  }

  // Verificamos si se emite "TransactionAccepted"
  // y luego finalizamos.
  // (O si se rota de nuevo, algo anda mal)
  let acceptEvent = lastRevealReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "TransactionAccepted"
  );
  if (!acceptEvent) {
    throw new Error("No 'TransactionAccepted' event found (did it fail?).");
  }

  console.log("\nFinalizing transaction...");
  const txFinal = await consensusMain.finalizeTransaction(ghostTxId);
  await txFinal.wait();

  // 12. Comprobar el estado final
  const finalTxData = await consensusData.getTransactionData(ghostTxId);
  console.log("Final transaction status:", finalTxData.status.toString());

  // 13. Comprobar balances
  const ghostBalance = await token.balanceOf(ghostAddress);
  const recipientBalance = await token.balanceOf(recipient);
  console.log("\nFinal balances:");
  console.log("- Ghost contract:", ethers.formatEther(ghostBalance), "TEST");
  console.log("- Recipient:", ethers.formatEther(recipientBalance), "TEST");

  if (finalTxData.status.toString() === "7") {
    console.log("\n¡Ghost deployment and leader rotation completed successfully! ✓");
  } else {
    throw new Error("Unexpected final status: " + finalTxData.status.toString());
  }
}

//
// ================ Ejecución ================
//
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
