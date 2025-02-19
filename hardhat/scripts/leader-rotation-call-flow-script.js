const hre = require("hardhat");

async function generateSignature(signer, currentSeed) {
  const seedBytes = ethers.zeroPadValue(ethers.toBeHex(currentSeed), 32);
  const vrfProof = await signer.signMessage(ethers.getBytes(seedBytes));
  return vrfProof;
}

async function completeConsensusFlow(
  consensusMain,
  genManager,
  txId,
  ghostAddress,
  activator,
  vrfProofActivate,
  validators,
  messages,
  voteType
) {
  let skipFinalize = false
	if (voteType > 10) {
		skipFinalize = true
		voteType = voteType - 10
	}
  // 1. Activate transaction
  const activateTx = await consensusMain.connect(activator).activateTransaction(txId, vrfProofActivate);
  const activationReceipt = await activateTx.wait();
  const activationEvent = activationReceipt.logs?.find(
		(log) => consensusMain.interface.parseLog(log)?.name === "TransactionActivated"
	)
	if (!activationEvent) throw new Error("TransactionActivated event not found");
  const activationParsedLog = consensusMain.interface.parseLog(activationEvent);
  console.log("Messages", messages);
	console.log("validators", validators.map((v) => v.address));

  // Get leader from activation event
  const leader = validators.find((v) => v.address === activationParsedLog?.args[1]);
	const validatorsForTx = activationParsedLog?.args[2].map((v) => findSignerByAddress(validators, v));

  const currentSeed = await genManager.recipientRandomSeed(ghostAddress);
	const vrfProofPropose1 = await generateSignature(leader, BigInt(currentSeed));

  // 2. Leader proposes receipt
  await consensusMain.connect(leader).proposeReceipt(txId, "0x123456", messages, vrfProofPropose1);

  // 3. Commit votes
  const nonces = [123, 456, 789, 1011, 1213];
  for (let i = 0; i < validatorsForTx.length; i++) {
		const voteHash = ethers.solidityPackedKeccak256(
			["address", "uint8", "uint256"],
			[validatorsForTx[i].address, voteType, nonces[i]]
		);
		await consensusMain.connect(validatorsForTx[i]).commitVote(txId, voteHash);
	}

  // 4. Reveal votes
  let tx = ""
  let receipt = ""
  for (let i = 0; i < validatorsForTx.length; i++) {
		const voteHash = ethers.solidityPackedKeccak256(
			["address", "uint8", "uint256"],
			[validatorsForTx[i].address, voteType, nonces[i]]
		);
		tx = await consensusMain.connect(validatorsForTx[i]).revealVote(txId, voteHash, voteType, nonces[i]);
	}

  // 5. Finalize transaction
  if (voteType === 1 && !skipFinalize) {
		// Agree Majority
		tx = await consensusMain.finalizeTransaction(txId);
		receipt = await tx.wait();
	} else if (voteType === 2) {
		// Disagree Majority
		receipt = await tx.wait();
	} else {
		receipt = await tx.wait();
	}

	return [receipt, leader];
}

async function main() {
  console.log("Starting ghost deployment and call flow...");

  // Get signers
  const [owner, validator1, validator2, validator3, validator4, validator5] = await hre.ethers.getSigners();
  const validators = [validator1, validator2, validator3, validator4, validator5];

  // Get contract instances
  const consensusMainAddress = require("../deployments/localhost/ConsensusMain.json").address;
  const consensusMain = await hre.ethers.getContractAt("ConsensusMain", consensusMainAddress);

  const consensusDataAddress = require("../deployments/localhost/ConsensusData.json").address;
  const consensusData = await hre.ethers.getContractAt("ConsensusData", consensusDataAddress);

  const genManagerAddress = require("../deployments/localhost/ConsensusManager.json").address;
  const genManager = await hre.ethers.getContractAt("ConsensusManager", genManagerAddress);

  const BasicERC20 = require("../deployments/localhost/BasicERC20.json").address;
  const BasicERC20Contract = await hre.ethers.getContractAt("BasicERC20", BasicERC20);

  // Deploy a dummy ERC20 token
  const token = await BasicERC20Contract.deploy("Test Token", "TEST", owner.address);
  await token.mint(owner.address, ethers.parseEther("1000"));

  const maxRotations = 2;

  // 1. Deploy ghost contract
  console.log("\n1. Deploying ghost contract...");
  const deployTx = await consensusMain.addTransaction(
    ethers.ZeroAddress,
    ethers.ZeroAddress,
    3,
    maxRotations,
    "0x1234"
  );
  const deployReceipt = await deployTx.wait();

  const deployEvent = deployReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction"
  );
  const deployParsedLog = consensusMain.interface.parseLog(deployEvent);
  const deployTxId = deployParsedLog.args[0];
  const ghostAddress = deployParsedLog.args[1];
  const deployActivator = validators.find((v) => v.address === deployParsedLog.args[2]);
  let currentSeed = await genManager.recipientRandomSeed(ghostAddress);
  const vrfProofActivate = await generateSignature(deployActivator, BigInt(currentSeed));

  console.log("- Deploy Transaction ID:", deployTxId);
  console.log("- Ghost Address:", ghostAddress);
  console.log("- Deploy Activator:", deployActivator.address);

  // 2. Complete consensus flow for ghost deployment
  console.log("\n2. Completing consensus flow for ghost deployment...");
  const deployStatus = await completeConsensusFlow(
    consensusMain,
    genManager,
    deployTxId,
    ghostAddress,
    deployActivator,
    vrfProofActivate,
    validators,
    [],
    1
  );

  // 3. Fund the ghost contract
  await token.transfer(ghostAddress, ethers.parseEther("100"));

  // 4. Create transfer transaction through ghost contract
  const GhostBlueprintAddress = require("../deployments/localhost/GhostBlueprint.json").address;
  const GhostBlueprint = await hre.ethers.getContractAt("GhostBlueprint", GhostBlueprintAddress);
  const ghost = GhostBlueprint.attach(ghostAddress);

  // 5. Encode the transfer function call
  const transferAmount = ethers.parseEther("50");
  const recipient = owner.address;
  const transferData = token.interface.encodeFunctionData("transfer", [recipient, transferAmount]);

  // 6. Add transaction through ghost
  const ghostTx = await ghost.addTransaction(numVoters, maxRotations, transferData);
  const ghostReceipt = await ghostTx.wait();
  const ghostEvent = ghostReceipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction"
  );
  const ghostParsedLog = consensusMain.interface.parseLog(ghostEvent);

  const ghostTxId = ghostParsedLog?.args[0];
  const ghostActivator = validators.find((v) => v.address === ghostParsedLog?.args[2]);

  // 7. Create message to be emitted on acceptance
  const abiCoder = new ethers.AbiCoder();
  const messageData = abiCoder.encode(["address", "bytes"], [token.target, transferData]);

  const message = {
    messageType: 0, // External
    recipient: ghostAddress,
    value: 0,
    data: messageData,
    onAcceptance: true, // Set to true to emit on acceptance
  };
  currentSeed = await genManager.recipientRandomSeed(ghostAddress);
  const vrfProofActivate2 = await generateSignature(ghostActivator, BigInt(currentSeed));

  // 8. Complete consensus for transfer with Disagree votes
  const voteType = 2 // Disagree
  const [receipt, leader] = await completeConsensusFlow(
    consensusMain,
    genManager,
    ghostTxId,
    ghostAddress,
    ghostActivator,
    vrfProofActivate2,
    validators,
    [message],
    voteType
  );

  // 9. Check for TransactionLeaderRotated event
  if (!receipt) throw new Error("Receipt not found");
  if (receipt.logs?.length === 0) throw new Error("No logs found in receipt");
  const event = receipt.logs?.find(
    (log) => consensusMain.interface.parseLog(log)?.name === "TransactionLeaderRotated"
  );
  if (!event) throw new Error("TransactionLeaderRotated event not found");
  const leaderRotatedParsedLog = consensusMain.interface.parseLog(event);
  const newLeader = validators.find((v) => v.address === leaderRotatedParsedLog?.args[1]);
  console.log("newLeader", newLeader.address);

  // 10. Verify the transfer did not occur
  console.log("token balance of ghost", await token.balanceOf(ghostAddress));
  console.log("token balance of recipient", await token.balanceOf(recipient));

  // 11. Get validators for the transaction, excluding the leader
  const txValidators = await consensusData.getValidatorsForLastRound(ghostTxId);

  console.log("txValidators", txValidators);
  const voters = txValidators.map((v) => findSignerByAddress(validators, v));

  // 12. New leader proposes new receipt
  const newProposedReceipt = "0x4567";
  const currentSeed2 = await genManager.recipientRandomSeed(ghostAddress);
  const vrfProofPropose = await generateSignature(newLeader, BigInt(currentSeed2));
  await consensusMain.connect(newLeader).proposeReceipt(ghostTxId, newProposedReceipt, [message], vrfProofPropose);

  // 13. Vote with Agree
  const agreeVoteType = 1;
  console.log("voters length", voters.length);
  for (let i = 0; i < voters.length; i++) {
    const nonce = 1234 + i;
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [voters[i].address, agreeVoteType, nonce]
    );
    await consensusMain.connect(voters[i]).commitVote(ghostTxId, voteHash);
  }

  for (let i = 0; i < voters.length; i++) {
    const nonce = 1234 + i;
    const voteHash = ethers.solidityPackedKeccak256(
      ["address", "uint8", "uint256"],
      [voters[i].address, agreeVoteType, nonce]
    );
    await consensusMain.connect(voters[i]).revealVote(ghostTxId, voteHash, agreeVoteType, nonce);
  }

  // const txData = await consensusData.getTransactionData(ghostTxId)
  // expect(txData.revealedVotesCount).to.equal(voters.length)
  // expect(txData.status).to.equal(5) // Accepted
  const txStatus = await consensusData.getTransactionStatus(ghostTxId);
  console.log("txStatus", txStatus);
  // 14. Finalize
  const tx = await consensusMain.finalizeTransaction(ghostTxId);
  const receiptFinalization = await tx.wait();
  console.log("receiptFinalization", receiptFinalization);
  console.log("txStatus", await consensusData.getTransactionStatus(ghostTxId));

  // Verify the transfer occurred
  console.log("token balance of ghost", await token.balanceOf(ghostAddress));
  console.log("token balance of recipient", await token.balanceOf(recipient));
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
