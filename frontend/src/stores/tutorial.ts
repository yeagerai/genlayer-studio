import { defineStore } from 'pinia';
import { useContractsStore } from './contracts';
import { useNodeStore } from './node';
import { useTransactionsStore } from './transactions';
import { useMockContractData } from '@/hooks/useMockContractData';
import contractBlob from '@/assets/examples/contracts/storage.py?raw';

const {
  mockContractId,
  mockDeployedContract,
  mockDeploymentTx,
  mockWriteMethodTx,
} = useMockContractData();

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
    transactionsStore.addTransaction(mockDeploymentTx);
    nodeStore.logs.push({
      scope: 'GenVM',
      name: 'deploying_contract',
      type: 'info',
      message: 'Deploying contract',
    });

    await sleep(1000);
    contractsStore.addDeployedContract(mockDeployedContract);

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

    setTimeout(() => {
      transactionsStore.updateTransaction({
        ...mockDeploymentTx,
        status: 'FINALIZED',
      });
    }, 1000);

    return mockDeployedContract;
  }

  async function expandReadMethod() {
    const method: HTMLElement | null = document.querySelector(
      '[data-testid="expand-method-btn-get_storage"]',
    );

    method?.click();
  }

  async function callReadMethod() {
    const method: HTMLElement | null = document.querySelector(
      '[data-testid="read-method-btn-get_storage"]',
    );

    nodeStore.logs.push({
      scope: 'GenVM',
      name: 'read_contract',
      type: 'info',
      message: 'Call method: get_storage',
      data: {
        method_name: 'get_storage',
        method_args: [],
        result: 'Hello world!',
        output: '',
      },
    });

    method?.click();
  }

  async function expandWriteMethod() {
    const method: HTMLElement | null = document.querySelector(
      '[data-testid="expand-method-btn-update_storage"]',
    );

    method?.click();
  }

  async function callWriteMethod() {
    const method: HTMLElement | null = document.querySelector(
      '[data-testid="write-method-btn-update_storage"]',
    );

    method?.click();

    nodeStore.logs.push({
      scope: 'GenVM',
      name: 'write_contract',
      type: 'info',
      message: 'Execute method: update_storage',
      data: {
        method_name: 'update_storage',
        method_args: ['Goodbye world'],
        output: '',
      },
    });

    transactionsStore.addTransaction(mockWriteMethodTx);

    setTimeout(() => {
      transactionsStore.updateTransaction({
        ...mockWriteMethodTx,
        status: 'FINALIZED',
      });
    }, 1000);
  }

  return {
    mockContractId,
    resetTutorialState,
    addAndOpenContract,
    deployMockContract,
    expandReadMethod,
    expandWriteMethod,
    callReadMethod,
    callWriteMethod,
  };
});
