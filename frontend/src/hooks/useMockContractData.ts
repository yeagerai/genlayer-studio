import { type DeployedContract, type TransactionItem } from '@/types';

export function useMockContractData() {
  const mockContractId = '1a621cad-1cfd-4dbd-892a-f6bbde7a2fab';
  const mockContractAddress = '0x3F9Fb6C6aBaBD0Ae6cB27c513E7b0fE4C0B3E9C8';
  const mockStorage = {
    storage: 'Hello World',
  };

  const mockDeployedContract: DeployedContract = {
    address: mockContractAddress,
    contractId: mockContractId,
    defaultState: `{"storage":"${mockStorage.storage}"}`,
  };

  const mockContractSchema = {
    class: 'Storage',
    abi: [
      {
        inputs: [
          {
            name: 'initial_storage',
            type: 'string',
            default: 'Hello World',
          },
        ],
        type: 'constructor',
      },
      {
        inputs: [],
        name: 'get_storage',
        outputs: 'string',
        type: 'function',
      },
      {
        inputs: [
          {
            name: 'new_storage',
            type: 'string',
            default: 'Goodbye World',
          },
        ],
        name: 'update_storage',
        outputs: '',
        type: 'function',
      },
    ],
  };

  const mockDeploymentTx: TransactionItem = {
    contractAddress: mockContractAddress,
    localContractId: mockContractId,
    hash: '0x123',
    type: 'deploy',
    status: 'PENDING',
    data: {},
  };

  const mockWriteMethodTx: TransactionItem = {
    contractAddress: mockContractAddress,
    localContractId: mockContractId,
    hash: '0x123',
    type: 'method',
    status: 'PENDING',
    data: {
      method_name: 'update_storage',
      method_args: ['Goodbye world'],
      output: '',
      data: {
        function_name: 'update_storage',
      },
    },
  };

  return {
    mockStorage,
    mockContractId,
    mockDeployedContract,
    mockContractSchema,
    mockDeploymentTx,
    mockWriteMethodTx,
  };
}
