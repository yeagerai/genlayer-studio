const { buildModule } = require("@nomicfoundation/hardhat-ignition/modules");

module.exports = buildModule("DeployFixture", (m) => {
    // Get accounts
    const owner = m.getAccount(0);
    const validator1 = m.getAccount(1);
    const validator2 = m.getAccount(2);
    const validator3 = m.getAccount(3);

    // Deploy base contracts
    const GhostContract = m.contract("GhostContract");
    const ConsensusManager = m.contract("ConsensusManager");
    const ConsensusMain = m.contract("ConsensusMain");

    // Initialize ConsensusMain
    const initConsensusMain = m.call(ConsensusMain, "initialize", [ConsensusManager], {
        after: [ConsensusManager]
    });

    const GhostFactory = m.contract("GhostFactory");
    const initGhostFactory = m.call(GhostFactory, "initialize", [], {
        after: [initConsensusMain]
    });

    const GhostBlueprint = m.contract("GhostBlueprint");
    const initGhostBlueprint = m.call(GhostBlueprint, "initialize", [owner], {
        after: [initGhostFactory]
    });

    const setBlueprint = m.call(GhostFactory, "setGhostBlueprint", [GhostBlueprint], {
        after: [initGhostBlueprint]
    });

    const deployProxy = m.call(GhostFactory, "deployNewBeaconProxy", [], {
        after: [setBlueprint]
    });

    // Important: Ensure that validator1.address is available before using it
    const MockGenStaking = m.contract("MockGenStaking", [validator1]);

    const Queues = m.contract("Queues");
    const Transactions = m.contract("Transactions");
    const Messages = m.contract("Messages");

    // Initialize contracts
    const initTransactions = m.call(Transactions, "initialize", [ConsensusMain], {
        after: [initConsensusMain]
    });
    const initQueues = m.call(Queues, "initialize", [ConsensusMain], {
        after: [initTransactions]
    });
    const initMessages = m.call(Messages, "initialize", [], {
        after: [initQueues]
    });

    // Set up contract connections
    const setGhostFactory = m.call(ConsensusMain, "setGhostFactory", [GhostFactory], {
        after: [initConsensusMain]
    });
    const setGenStaking = m.call(ConsensusMain, "setGenStaking", [MockGenStaking], {
        after: [setGhostFactory]
    });
    const setGenQueue = m.call(ConsensusMain, "setGenQueue", [Queues], {
        after: [setGenStaking]
    });
    const setGenTransactions = m.call(ConsensusMain, "setGenTransactions", [Transactions], {
        after: [setGenQueue]
    });
    const setGenMessages = m.call(ConsensusMain, "setGenMessages", [Messages], {
        after: [setGenTransactions]
    });

    // Deploy and initialize ConsensusData
    const ConsensusData = m.contract("ConsensusData");
    const initConsensusData = m.call(ConsensusData, "initialize", [ConsensusMain, Transactions, Queues], {
        after: [setGenMessages]
    });

    // Set remaining connections
    const setGenConsensusByGhostFactory = m.call(GhostFactory, "setGenConsensus", [ConsensusMain], {
        after: [initConsensusData]
    });
    const setGhostManagerByGhostFactory = m.call(GhostFactory, "setGhostManager", [ConsensusMain], {
        after: [setGenConsensusByGhostFactory]
    });
    const setGenConsensusByTransactions = m.call(Transactions, "setGenConsensus", [ConsensusMain], {
        after: [setGhostManagerByGhostFactory]
    });
    const setGenConsensusByMessages = m.call(Messages, "setGenConsensus", [ConsensusMain], {
        after: [setGenConsensusByTransactions]
    });
    const setGenTransactionsByMessages = m.call(Messages, "setGenTransactions", [Transactions], {
        after: [setGenConsensusByMessages]
    });
    const setAcceptanceTimeout = m.call(ConsensusMain, "setAcceptanceTimeout", [0], {
        after: [setGenTransactionsByMessages]
    });

    // Setup validators
    const addValidators = m.call(MockGenStaking, "addValidators", [[validator1, validator2, validator3]], {
        after: [setAcceptanceTimeout]
    });

    // Verify validators are correctly set up
    const verifyValidatorCount = m.call(MockGenStaking, "getValidatorCount", [], {
        after: [addValidators],
        id: "verifyValidatorCount"
    });

    // Verify that each validator is registered
    const verifyValidator1 = m.call(MockGenStaking, "isValidator", [validator1], {
        after: [verifyValidatorCount],
        id: "verifyValidator1"
    });

    const verifyValidator2 = m.call(MockGenStaking, "isValidator", [validator2], {
        after: [verifyValidator1],
        id: "verifyValidator2"
    });
    const verifyValidator3 = m.call(MockGenStaking, "isValidator", [validator3], {
        after: [verifyValidator2],
        id: "verifyValidator3"
    });


    return {
        GhostContract,
        ConsensusManager,
        ConsensusMain,
        GhostFactory,
        GhostBlueprint,
        MockGenStaking,
        Queues,
        Transactions,
        Messages,
        ConsensusData
    };
});