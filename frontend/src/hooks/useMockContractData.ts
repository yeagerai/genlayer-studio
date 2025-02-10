import { type DeployedContract, type TransactionItem } from '@/types';

export function useMockContractData() {
  const mockContractId = '1a621cad-1cfd-4dbd-892a-f6bbde7a2fab';
  const mockContractAddress = '0x3F9Fb6C6aBaBD0Ae6cB27c513E7b0fE4C0B3E9C8';

  const mockDeployedContract: DeployedContract = {
    address: mockContractAddress,
    contractId: mockContractId,
    defaultState: '{}',
  };

  const mockContractSchema = {
    ctor: {
      kwparams: {},
      params: [['initial_storage', 'string']],
    },
    methods: {
      get_storage: {
        kwparams: {},
        params: [],
        readonly: true,
        ret: 'string',
      },
      update_storage: {
        kwparams: {},
        params: [['new_storage', 'string']],
        readonly: false,
        ret: 'null',
      },
    },
  };

  // FIXME:
  const mockDeploymentTx: TransactionItem = {
    contractAddress: mockContractAddress,
    localContractId: mockContractId,
    hash: '0x123',
    type: 'deploy',
    status: 'FINALIZED',
    data: {},
  };

  return {
    mockContractId,
    mockDeployedContract,
    mockContractSchema,
    mockDeploymentTx,
  };
}
