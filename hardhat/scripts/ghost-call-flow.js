const hre = require("hardhat");

async function generateSignature(signer, currentSeed) {
  const seedBytes = ethers.zeroPadValue(ethers.toBeHex(currentSeed), 32);
  const vrfProof = await signer.signMessage(ethers.getBytes(seedBytes));
  return vrfProof;
}

async function completeConsensusFlow(
  consensusMain,
  txId,
  ghostAddress,
  activator,
  validators,
  proposedReceipt = "0x1234",
  nonces,
) {
  // 1. Activate transaction
  const currentSeed = await consensusMain.recipientRandomSeed(ghostAddress);
  const vrfProofActivate = await generateSignature(
    activator,
    BigInt(currentSeed),
  );
  const activateTx = await consensusMain
    .connect(activator)
    .activateTransaction(txId, vrfProofActivate);
  const activationReceipt = await activateTx.wait();
  if (!activationReceipt) throw new Error("Transaction activation failed");

  // Get leader from activation event
  const activationEvent = activationReceipt.logs?.find(
    (log) =>
      consensusMain.interface.parseLog(log)?.name === "TransactionActivated",
  );
  if (!activationEvent) throw new Error("TransactionActivated event not found");
  const leader = validators.find(
    (v) =>
      v.address === consensusMain.interface.parseLog(activationEvent).args[1],
  );

  // 2. Leader proposes receipt
  const currentSeedForProposal =
    await consensusMain.recipientRandomSeed(ghostAddress);
  const vrfProofPropose = await generateSignature(
    leader,
    BigInt(currentSeedForProposal),
  );
  const proposeReceipt = await consensusMain
    .connect(leader)
    .proposeReceipt(txId, proposedReceipt, [], vrfProofPropose);
  const proposeReceiptReceipt = await proposeReceipt.wait();
  if (!proposeReceiptReceipt) throw new Error("Transaction proposal failed");

  // 3. Commit votes
  const voteType = 1; // Agree
  for (let i = 0; i < validators.length; i++) {
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [validators[i].address, voteType, nonces[i]],
    );
    await consensusMain
      .connect(validators[i])
      .commitVote(txId, voteHash, false);
  }

  // 4. Reveal votes
  for (let i = 0; i < validators.length; i++) {
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [validators[i].address, voteType, nonces[i]],
    );
    await consensusMain
      .connect(validators[i])
      .revealVote(txId, voteHash, voteType, nonces[i], false);
  }

  // 5. Finalize transaction
  await consensusMain.finalizeTransaction(txId);
  return await consensusMain.txStatus(txId);
}

async function main() {
  console.log("Starting ghost deployment and call flow...");

  // Get signers
  const [owner, validator1, validator2, validator3] =
    await hre.ethers.getSigners();
  const validators = [validator1, validator2, validator3];

  // Get contract instances
  const consensusMainAddress =
    require("../deployments/localhost/ConsensusMain.json").address;
  console.log("🚀 ~ main ~ consensusMainAddress:", consensusMainAddress);
  const consensusMain = await hre.ethers.getContractAt(
    "ConsensusMain",
    consensusMainAddress,
  );

  const maxRotations = 2;

  // 1. Deploy ghost contract
  console.log("\n1. Deploying ghost contract...");
  const deployTx = await consensusMain.addTransaction(
    ethers.ZeroAddress,
    ethers.ZeroAddress,
    3,
    maxRotations,
    "0x",
  );
  const deployReceipt = await deployTx.wait();

  const deployEvent = deployReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction",
  );
  const deployParsedLog = consensusMain.interface.parseLog(deployEvent);
  const deployTxId = deployParsedLog.args[0];
  const ghostAddress = deployParsedLog.args[1];
  const deployActivator = validators.find(
    (v) => v.address === deployParsedLog.args[2],
  );

  console.log("- Deploy Transaction ID:", deployTxId);
  console.log("- Ghost Address:", ghostAddress);
  console.log("- Deploy Activator:", deployActivator.address);

  // Complete consensus flow for ghost deployment
  console.log("\n2. Completing consensus flow for ghost deployment...");
  const deployStatus = await completeConsensusFlow(
    consensusMain,
    deployTxId,
    ghostAddress,
    deployActivator,
    validators,
    "0x123456",
    [123, 456, 789], // deployNonces
  );
  console.log("- Ghost deployment status:", deployStatus.toString());

  // Verify ghost contract owner
  const GhostBlueprint = await hre.ethers.getContractFactory("GhostBlueprint");
  const ghost = GhostBlueprint.attach(ghostAddress);
  const ghostOwner = await ghost.owner();
  console.log("- Ghost contract owner:", ghostOwner);
  console.log("- ConsensusMain address:", consensusMain.target);

  // 3. Create dummy call through ghost contract
  console.log("\n3. Creating dummy call through ghost contract...");
  const dummyCallTx = await ghost.addTransaction(
    3,
    maxRotations,
    ethers.keccak256(ethers.toUtf8Bytes("dummyFunction()")),
  );
  const dummyCallReceipt = await dummyCallTx.wait();

  const dummyCallEvent = dummyCallReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction",
  );
  const dummyCallParsedLog = consensusMain.interface.parseLog(dummyCallEvent);
  const dummyCallTxId = dummyCallParsedLog.args[0];
  const dummyCallActivator = validators.find(
    (v) => v.address === dummyCallParsedLog.args[2],
  );

  console.log("- Dummy Call Transaction ID:", dummyCallTxId);
  console.log("- Dummy Call Activator:", dummyCallActivator.address);

  // Complete consensus flow for dummy call
  console.log("\n4. Completing consensus flow for dummy call...");
  const dummyCallStatus = await completeConsensusFlow(
    consensusMain,
    dummyCallTxId,
    ghostAddress,
    dummyCallActivator,
    validators,
    "0x123456",
    [123, 456, 789], // deployNonces
  );
  console.log("- Dummy call status:", dummyCallStatus.toString());

  if (deployStatus.toString() === "6" && dummyCallStatus.toString() === "6") {
    console.log("\n¡Ghost deployment and dummy call completed successfully! ✓");
  } else {
    throw new Error(
      `Unexpected final status: Deploy=${deployStatus}, DummyCall=${dummyCallStatus}`,
    );
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
