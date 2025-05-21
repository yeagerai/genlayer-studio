import { defineStore } from 'pinia';
import { useContractsStore } from './contracts';
import { useNodeStore } from './node';
import { useTransactionsStore } from './transactions';
import { useMockContractData } from '@/hooks/useMockContractData';
import contractBlob from '@/assets/examples/contracts/storage.py?raw';

const { mockContractId, mockDeployedContract, mockDeploymentTx } =
  useMockContractData();

export const useTutorialStore = defineStore('tutorialStore', () => {
  const contractsStore = useContractsStore();
  const transactionsStore = useTransactionsStore();
  const nodeStore = useNodeStore();

  const resetTutorialState = () => {
    contractsStore.removeContractFile(mockContractId);
    contractsStore.removeDeployedContract(mockContractId);
    transactionsStore.transactions.forEach((t) => {
      if (t.localContractId === mockContractId) {
        transactionsStore.removeTransaction(t);
      }
    });
  };

  async function addAndOpenContract() {
    const contractFile = {
      id: mockContractId,
      name: 'tutorial_storage.py',
      content: ((contractBlob as string) || '').trim(),
      example: true,
    };

    contractsStore.addContractFile(contractFile, true);
    contractsStore.openFile(mockContractId);
  }

  async function deployMockContract() {
    // For now we instantly mock the deployment of contract
    // In the future, we can improve this by properly mocking through the single contract store like for the schema
    // and thus preserve the appearance of async delays / loading times

    contractsStore.addDeployedContract(mockDeployedContract);

    nodeStore.logs.push({
      scope: 'GenVM',
      name: 'deploying_contract',
      type: 'info',
      message: 'Deploying contract',
    });

    nodeStore.logs.push({
      scope: 'GenVM',
      name: 'deployed_contract',
      type: 'success',
      message: 'Deployed contract',
      data: {
        id: mockDeployedContract.address,
        data: {
          state: mockDeployedContract.defaultState,
        },
      },
    });

    transactionsStore.addTransaction(mockDeploymentTx);

    return mockDeployedContract;
  }

  return {
    mockContractId,
    resetTutorialState,
    addAndOpenContract,
    deployMockContract,
  };
});
