const { buildModule } = require("@nomicfoundation/hardhat-ignition/modules");

module.exports = buildModule("DeployFixture", (m) => {
    // Get accounts
    const owner = m.getAccount(0);
    const validator1 = m.getAccount(1);
    const validator2 = m.getAccount(2);
    const validator3 = m.getAccount(3);
    const validator4 = m.getAccount(4);
    const validator5 = m.getAccount(5);

    // Deploy libraries first using m.library()
    const ArrayUtils = m.library("ArrayUtils");
    const RandomnessUtils = m.library("RandomnessUtils");

    // Then link them to contracts
    const Transactions = m.contract("Transactions", [], {
        libraries: {
            ArrayUtils: ArrayUtils
        },
        after: [ArrayUtils]
    });

    // Deploy base contracts with libraries
    const GhostContract = m.contract("GhostContract");
    const ConsensusManager = m.contract("ConsensusManager");

    const GhostFactory = m.contract("GhostFactory");
    const initGhostFactory = m.call(GhostFactory, "initialize", []);

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
    const MockGenStaking = m.contract("MockGenStaking");

    const Queues = m.contract("Queues");
    const Messages = m.contract("Messages");

    // Deploy utility contracts
    const FeeManager = m.contract("FeeManager");
    const Utils = m.contract("Utils");

    // Deploy contracts with libraries and constructor arguments
    const Rounds = m.contract("Rounds", [MockGenStaking, FeeManager, Utils], {
        libraries: {
            ArrayUtils: ArrayUtils,
            RandomnessUtils: RandomnessUtils
        },
        after: [ArrayUtils, RandomnessUtils]
    });

    const Voting = m.contract("Voting");

    const Idleness = m.contract("Idleness", [Transactions, MockGenStaking, Utils], {
        libraries: {
            ArrayUtils: ArrayUtils
        },
        after: [ArrayUtils]
    });

    // Important: Ensure that validator1.address is available before using it
    const ConsensusMain = m.contract("ConsensusMain");

    // Initialize ConsensusMain
    const initConsensusMain = m.call(ConsensusMain, "initialize", [], {
        after: [ConsensusMain]
    });

    // Initialize contracts en orden correcto
    const initTransactions = m.call(Transactions, "initialize", [ConsensusMain], {
        after: [initConsensusMain, Rounds, Voting, Idleness, Utils]
    });

    const initQueues = m.call(Queues, "initialize", [ConsensusMain], {
        after: [initTransactions]
    });

    const initMessages = m.call(Messages, "initialize", [], {
        after: [initQueues]
    });

    // Set external contracts with additional contracts
    const setExternalContracts = m.call(ConsensusMain, "setExternalContracts", [
        GhostFactory,
        ConsensusManager,
        Transactions,
        Queues,
        MockGenStaking,
        Messages,
        Idleness
    ], {
        after: [initMessages]
    });

    // Modificamos el orden: primero configuramos Transactions
    const setTransactionsExternals = m.call(Transactions, "setExternalContracts", [
        ConsensusMain,
        MockGenStaking,
        Rounds,
        Voting,
        Idleness,
        Utils
    ], {
        after: [setExternalContracts]
    });

    // Aseguramos que ConsensusData se inicialice después de que Transactions esté completamente configurado
    const ConsensusData = m.contract("ConsensusData");
    const initConsensusData = m.call(ConsensusData, "initialize", [ConsensusMain, Transactions, Queues], {
        after: [setTransactionsExternals]
    });

    // Set remaining connections
    const setGenConsensusByGhostFactory = m.call(GhostFactory, "setGenConsensus", [ConsensusMain], {
        after: [initConsensusData]
    });
    const setGhostManagerByGhostFactory = m.call(GhostFactory, "setGhostManager", [ConsensusMain], {
        after: [setGenConsensusByGhostFactory]
    });
    const setGenConsensusByMessages = m.call(Messages, "setGenConsensus", [ConsensusMain], {
        after: [setGenConsensusByGhostFactory]
    });
    const setGenTransactionsByMessages = m.call(Messages, "setGenTransactions", [Transactions], {
        after: [setGenConsensusByMessages]
    });

    // Setup validators
    const addValidators = m.call(MockGenStaking, "addValidators", [[validator1, validator2, validator3, validator4, validator5]], {
        after: [setGenTransactionsByMessages]
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
    const verifyValidator4 = m.call(MockGenStaking, "isValidator", [validator4], {
        after: [verifyValidator3],
        id: "verifyValidator4"
    });
    const verifyValidator5 = m.call(MockGenStaking, "isValidator", [validator5], {
        after: [verifyValidator4],
        id: "verifyValidator5"
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
        ConsensusData,
        ArrayUtils,
        RandomnessUtils,
        FeeManager,
        Utils,
        Rounds,
        Voting,
        Idleness
    };
});
