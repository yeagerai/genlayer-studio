import {
  useAccountsStore,
  useContractsStore,
  useTransactionsStore,
  useNodeStore,
  useTutorialStore,
  useConsensusStore,
} from '@/stores';
import {
  useDb,
  useGenlayer,
  useTransactionListener,
  useContractListener,
} from '@/hooks';
import { v4 as uuidv4 } from 'uuid';

export const useSetupStores = () => {
  const setupStores = async () => {
    const contractsStore = useContractsStore();
    const accountsStore = useAccountsStore();
    const transactionsStore = useTransactionsStore();
    const nodeStore = useNodeStore();
    const consensusStore = useConsensusStore();
    const tutorialStore = useTutorialStore();
    const db = useDb();
    const genlayer = useGenlayer();
    const transactionListener = useTransactionListener();
    const contractListener = useContractListener();
    const contractFiles = await db.contractFiles.toArray();
    const exampleFiles = contractFiles.filter((c) => c.example);

    if (exampleFiles.length === 0) {
      const contractsBlob = import.meta.glob(
        '@/assets/examples/contracts/*.py',
        {
          query: '?raw',
          import: 'default',
        },
      );
      for (const key of Object.keys(contractsBlob)) {
        const raw = await contractsBlob[key]();
        const name = key.split('/').pop() || 'ExampleContract.py';
        if (!contractFiles.some((c) => c.name === name)) {
          const contract = {
            id: uuidv4(),
            name,
            content: ((raw as string) || '').trim(),
            example: true,
          };
          contractsStore.addContractFile(contract);
        }
      }
    } else {
      contractsStore.contracts = await db.contractFiles.toArray();
    }

    contractsStore.deployedContracts = await db.deployedContracts.toArray();
    transactionsStore.transactions = await db.transactions.toArray();

    transactionsStore.initSubscriptions();
    transactionsStore.refreshPendingTransactions();
    transactionListener.init();
    contractListener.init();
    contractsStore.getInitialOpenedFiles();
    tutorialStore.resetTutorialState();
    nodeStore.getValidatorsData();
    nodeStore.getProvidersData();
    consensusStore.fetchFinalityWindowTime();

    if (accountsStore.accounts.length < 1) {
      await accountsStore.generateNewAccount();
    }

    genlayer.initClient();
  };

  return {
    setupStores,
  };
};
