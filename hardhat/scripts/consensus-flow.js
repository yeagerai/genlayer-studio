const hre = require("hardhat");


async function generateSignature(signer, currentSeed) {
    const seedBytes = ethers.zeroPadValue(ethers.toBeHex(currentSeed), 32);
    const vrfProof = await signer.signMessage(ethers.getBytes(seedBytes));
    return vrfProof;
}

async function main() {
    console.log("Starting consensus flow...");

    // Get signers
    const [owner, validator1, validator2, validator3] = await hre.ethers.getSigners();
    const validators = [validator1, validator2, validator3];

    // Get contract instances
    const consensusMainAddress = require("../deployments/localhost/ConsensusMain.json").address;
    const consensusDataAddress = require("../deployments/localhost/ConsensusData.json").address;
    const consensusMain = await hre.ethers.getContractAt("ConsensusMain", consensusMainAddress);
    const consensusData = await hre.ethers.getContractAt("ConsensusData", consensusDataAddress);

    const txAddTransactionInput = consensusMain.addTransaction.getFragment(
        ethers.ZeroAddress, // sender (will use msg.sender)
        ethers.ZeroAddress, // recipient (will create ghost)
        3, // number of validators
        "0x" // transaction data
    );

    const txFlowData = {
        addTransaction: {
            input: txAddTransactionInput,
        },
    }

    // 1. Add transaction
    console.log("\n1. Adding transaction...");
    const tx = await consensusMain.addTransaction(
        ethers.ZeroAddress,
        ethers.ZeroAddress,
        3,
        "0x"
    );
    const receipt = await tx.wait();
    txFlowData.addTransaction.output = {
        receipt,
    }

    // Find the NewTransaction event
    const newTxEvent = receipt.logs?.find(
        (log) => consensusMain.interface.parseLog(log)?.name === "NewTransaction"
    );
    if (!newTxEvent) throw new Error("NewTransaction event not found");

    const parsedLog = consensusMain.interface.parseLog(newTxEvent);
    const txId = parsedLog.args[0];
    const ghostAddress = parsedLog.args[1];
    const activatorAddress = parsedLog.args[2];

    console.log("- Transaction ID:", txId);
    console.log("- Ghost Address:", ghostAddress);
    console.log("- Activator:", activatorAddress);

    const activator = validators.find(v => v.address === activatorAddress);
    console.log("- Activator in consensus:", activator.address);

    // After each major step, get and store transaction data
    let txData = await consensusData.getTransactionData(txId);
    console.log("Initial transaction data:", txData);

    // 2. Activate transaction
    console.log("\n2. Activating transaction...");
    const currentSeed = await consensusMain.recipientRandomSeed(ghostAddress);
    const vrfProofActivate = await generateSignature(activator, BigInt(currentSeed));
    const activateTx = await consensusMain.connect(activator).activateTransaction(txId, vrfProofActivate);
    const txActivateTransactionInput = consensusMain.activateTransaction.getFragment(txId, vrfProofActivate);

    const activationReceipt = await activateTx.wait();
    txData = await consensusData.getTransactionData(txId);
    console.log("Transaction data after activation:", txData);

    const leaderAddress = consensusMain.interface.parseLog(activationReceipt.logs[0]).args[1];
    const leader = validators.find(v => v.address === leaderAddress);

    // 3. Propose receipt
    console.log("\n3. Proposing receipt...");
    const vrfProofPropose = await generateSignature(leader, BigInt(await consensusMain.recipientRandomSeed(ghostAddress)));
    const txProposalInput = consensusMain.proposeReceipt.getFragment(
        txId,
        "0x1234",
        [],
        vrfProofPropose
    )
    const txProposal = await consensusMain
        .connect(leader)
        .proposeReceipt(txId, "0x1234", [], vrfProofPropose);

    const txProposalReceipt = await txProposal.wait()
    txData = await consensusData.getTransactionData(txId);
    console.log("Transaction data after proposal:", txData);

    // 4. Commit votes
    console.log("\n4. Committing votes...");
    const voteType = 1; // Agree
    const nonces = [123, 456, 789];

    const voteHash1 = ethers.solidityPackedKeccak256(
        ["address", "uint8", "uint256"],
        [validator1.address, voteType, nonces[0]]
    )
    const voteHash2 = ethers.solidityPackedKeccak256(
        ["address", "uint8", "uint256"],
        [validator2.address, voteType, nonces[1]]
    )
    const voteHash3 = ethers.solidityPackedKeccak256(
        ["address", "uint8", "uint256"],
        [validator3.address, voteType, nonces[2]]
    )
    await consensusMain.connect(validator1).commitVote(txId, voteHash1, false)
    await consensusMain.connect(validator2).commitVote(txId, voteHash2, false)
    const txCommitVoteInput = consensusMain.commitVote.getFragment(txId, voteHash3, false)
    const lastCommitTx = await consensusMain.connect(validator3).commitVote(txId, voteHash3, false)
    const lastCommitTxReceipt = await lastCommitTx.wait()
    txData = await consensusData.getTransactionData(txId);
    console.log("Transaction data after commits:", txData);

    // 5. Reveal votes
    await consensusMain.connect(validator1).revealVote(txId, voteHash1, voteType, nonces[0])
    await consensusMain.connect(validator2).revealVote(txId, voteHash2, voteType, nonces[1])
    const revealVoteInput3 = consensusMain.revealVote.getFragment(txId, voteHash3, voteType, nonces[2])
    const revealReceipt3 = await consensusMain.connect(validator3).revealVote(txId, voteHash3, voteType, nonces[2])
    const revealReceipt3Receipt = await revealReceipt3.wait()
    txData = await consensusData.getTransactionData(txId);
    console.log("Transaction data after reveals:", txData);

    // 6. Finalize transaction
    console.log("\n6. Finalizing transaction...");
    const txFinalizeTransactionInput = consensusMain.finalizeTransaction.getFragment(txId)
    const finalizeTx = await consensusMain.finalizeTransaction(txId)
    const finalizeTxReceipt = await finalizeTx.wait()
    txData = await consensusData.getTransactionData(txId);
    console.log("Final transaction data:", txData);

    const finalStatus = await consensusMain.txStatus(txId);
    console.log("- Final transaction status:", finalStatus.toString());

    // Store all transaction data in the flow data
    Object.assign(txFlowData, {
        transactionData: {
            initial: txData,
            afterActivation: txData,
            afterProposal: txData,
            afterCommits: txData,
            afterReveals: txData,
            final: txData
        }
    });

    if (finalStatus.toString() === "6") {
        console.log("\n¡Consensus flow completed successfully! ✓");
        console.log(txFlowData)
    } else {
        throw new Error(`Unexpected final status: ${finalStatus}`);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });