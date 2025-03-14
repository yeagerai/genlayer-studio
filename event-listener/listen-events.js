const { ethers } = require("ethers");

// Full ABI with all events
const CONTRACT_ABI = [
    // Functions
    "function emitNewTransaction(bytes32 tx_id, address recipient, address activator)",
    "function emitTransactionActivated(bytes32 tx_id, address leader, address[] validators)",
    "function emitTransactionLeaderRotated(bytes32 tx_id, address newLeader)",
    "function emitTransactionReceiptProposed(bytes32 tx_id)",
    "function emitVoteCommitted(bytes32 tx_id, address validator, bool isLastVote)",
    "function emitVoteRevealed(bytes32 tx_id, address validator, uint8 voteType, bool isLastVote, uint8 result)",
    "function emitTransactionAccepted(bytes32 tx_id)",
    "function emitTransactionFinalized(bytes32 tx_id)",
    "function emitAppealStarted(bytes32 tx_id, address appealer, uint256 appealBond, address[] appealValidators)",

    // Events
    "event NewTransaction(bytes32 indexed tx_id, address indexed recipient, address indexed activator)",
    "event TransactionLeaderRotated(bytes32 indexed tx_id, address indexed newLeader)",
    "event TransactionActivated(bytes32 indexed tx_id, address indexed leader, address[] validators)",
    "event TransactionReceiptProposed(bytes32 indexed tx_id)",
    "event TransactionLeaderTimeout(bytes32 indexed tx_id)",
    "event VoteCommitted(bytes32 indexed tx_id, address indexed validator, bool isLastVote)",
    "event VoteRevealed(bytes32 indexed tx_id, address indexed validator, uint8 voteType, bool isLastVote, uint8 result)",
    "event TransactionAccepted(bytes32 indexed tx_id)",
    "event TransactionFinalized(bytes32 indexed tx_id)",
    "event TransactionNeedsRecomputation(bytes32[] tx_ids)",
    "event AppealStarted(bytes32 indexed tx_id, address indexed appealer, uint256 appealBond, address[] appealValidators)",
    "event InternalMessageProcessed(bytes32 indexed tx_id, address indexed recipient, address indexed activator)",
    "event TransactionCancelled(bytes32 indexed tx_id, address indexed sender)",
    "event TransactionIdleValidatorReplaced(bytes32 indexed tx_id, address indexed oldValidator, address indexed newValidator)"
];

async function listenToEvents() {
    const provider = new ethers.JsonRpcProvider("http://localhost:8545", {
        chainId: 61999,
        name: "genlayer-local"
    });

    const contractAddress = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
    const contract = new ethers.Contract(contractAddress, CONTRACT_ABI, provider);
    const iface = new ethers.Interface(CONTRACT_ABI);

    console.log("Starting to listen for events...");
    console.log("Connected to network:", await provider.getNetwork());
    console.log("Watching contract:", contractAddress);

    // Listen for all events
    contract.on("*", (event) => {
        console.log("\nEvent Detected:", event.eventName);
        console.log("Parameters:", event.args);
    });

    // Listen for pending transactions
    provider.on("pending", async (txHash) => {
        if (txHash) {
            try {
                const tx = await provider.getTransaction(txHash);
                if (tx?.to?.toLowerCase() === contractAddress.toLowerCase()) {
                    console.log("\nPending Transaction:", txHash);
                    console.log("\nTransaction to contract:");
                    console.log("- From:", tx.from);
                    console.log("- To:", tx.to);

                    // Decode the input data
                    if (tx.data) {
                        try {
                            const decodedData = iface.parseTransaction({ data: tx.data });
                            console.log("\nDecoded Function Call:");
                            console.log("- Function:", decodedData.name);
                            console.log("- Arguments:");
                            decodedData.args.forEach((arg, index) => {
                                console.log(`  arg[${index}]:`, arg.toString());
                            });
                        } catch (e) {
                            console.log("Raw transaction data:", tx.data);
                        }
                    }

                    // Wait for receipt
                    console.log("\nWaiting for receipt...");
                    const receipt = await provider.waitForTransaction(txHash);
                    console.log("\nTransaction mined in block:", receipt.blockNumber);
                    console.log("Status:", receipt.status ? "Success" : "Failed");
                    console.log("Gas used:", receipt.gasUsed.toString());
                }
            } catch (e) {
                console.log("Error processing transaction:", e.message);
            }
        }
    });
}

// Run the function
listenToEvents()
    .catch(error => {
        console.error("Initial setup error:", error);
    });

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\nStopping event listener...');
    process.exit();
});