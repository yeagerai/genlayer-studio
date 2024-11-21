import { watch, ref, computed } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import type { Address, TransactionItem } from '@/types';
import {
  useContractsStore,
  useTransactionsStore,
  useAccountsStore,
} from '@/stores';
import { useDebounceFn } from '@vueuse/core';
import { notify } from '@kyvg/vue3-notification';
import { useMockContractData } from './useMockContractData';
import { useEventTracking, useRpcClient, useWallet } from '@/hooks';
import * as calldata from '@/calldata';

const schema = ref<any>();

export function useContractQueries() {
  const rpcClient = useRpcClient();
  const accountsStore = useAccountsStore();
  const transactionsStore = useTransactionsStore();
  const contractsStore = useContractsStore();
  const queryClient = useQueryClient();
  const { trackEvent } = useEventTracking();
  const wallet = useWallet();
  const contract = computed(() => contractsStore.currentContract);

  const { mockContractId, mockContractSchema, mockStorage } =
    useMockContractData();

  const isMock = computed(() => contract.value?.id === mockContractId);

  const deployedContract = computed(() =>
    contractsStore.deployedContracts.find(
      ({ contractId }) => contractId === contract.value?.id,
    ),
  );

  const isDeployed = computed(() => !!deployedContract.value);
  const address = computed(() => deployedContract.value?.address);

  const fetchContractSchemaDebounced = useDebounceFn(() => {
    return fetchContractSchema();
  }, 300);

  watch(
    () => contract.value?.content,
    () => {
      queryClient.invalidateQueries({
        queryKey: ['schema', contract.value?.id],
      });
    },
  );

  const contractSchemaQuery = useQuery({
    queryKey: ['schema', () => contract.value?.id],
    queryFn: fetchContractSchemaDebounced,
    refetchOnWindowFocus: false,
    retry: 0,
    enabled: !!contract.value?.id,
  });

  async function fetchContractSchema() {
    if (isMock.value) {
      return mockContractSchema;
    }

    const result = await rpcClient.getContractSchema({
      code: contract.value?.content ?? '',
    });

    schema.value = result;

    return schema.value;
  }

  const isDeploying = ref(false);

  async function deployContract(
    args: calldata.CalldataEncodable[],
    leaderOnly: boolean,
  ) {
    isDeploying.value = true;

    try {
      if (!contract.value || !accountsStore.currentPrivateKey) {
        throw new Error('Error Deploying the contract');
      }
      const data = [
        contract.value?.content ?? '',
        calldata.encode({ args }),
        leaderOnly,
      ];

      const nonce = await accountsStore.getCurrentNonce();

      const signed = await wallet.signTransaction({
        privateKey: accountsStore.currentPrivateKey,
        data,
        nonce,
      });
      const result = await rpcClient.sendTransaction(signed);
      const tx: TransactionItem = {
        contractAddress: '',
        localContractId: contract.value?.id ?? '',
        hash: result,
        type: 'deploy',
        status: 'PENDING',
        data: {},
      };

      notify({
        title: 'Started deploying contract',
        type: 'success',
      });

      trackEvent('deployed_contract', {
        contract_name: contract.value?.name || '',
      });

      transactionsStore.clearTransactionsForContract(contract.value?.id ?? '');
      transactionsStore.addTransaction(tx);
      contractsStore.removeDeployedContract(contract.value?.id ?? '');
      return tx;
    } catch (error) {
      isDeploying.value = false;
      notify({
        type: 'error',
        title: 'Error deploying contract',
      });
      throw new Error('Error Deploying the contract');
    }
  }

  const abiQueryEnabled = computed(
    () => !!contract.value && !!isDeployed.value,
  );

  const contractAbiQuery = useQuery({
    queryKey: [
      'abi',
      () => contract.value?.id,
      () => deployedContract.value?.address,
    ],
    queryFn: fetchContractAbi,
    enabled: abiQueryEnabled,
    refetchOnWindowFocus: false,
    retry: 2,
  });

  async function fetchContractAbi() {
    if (isMock.value) {
      return mockContractSchema;
    }

    const result = await rpcClient.getDeployedContractSchema({
      address: deployedContract.value?.address ?? '',
    });

    return result;
  }

  async function callReadMethod(
    method: string,
    args: calldata.CalldataEncodable[],
  ) {
    if (isMock.value) {
      return mockStorage.storage;
    }

    try {
      const data = [calldata.encode({ method, args })];
      const encodedData = wallet.encodeTransactionData(data);

      const result = await rpcClient.getContractState({
        to: address.value || '',
        from: accountsStore.currentUserAddress,
        data: encodedData,
      });

      return result;
    } catch (error) {
      console.error(error);
      throw new Error('Error getting the contract state');
    }
  }

  async function callWriteMethod({
    method,
    args,
    leaderOnly,
  }: {
    method: string;
    args: calldata.CalldataEncodable[];
    leaderOnly: boolean;
  }) {
    if (isMock.value) {
      mockStorage.storage = params[0];
      return true;
    }

    try {
      if (!accountsStore.currentPrivateKey) {
        throw new Error('Error Deploying the contract');
      }
      const data = [calldata.encode({ method, args }), leaderOnly];
      const to = (address.value as Address) || null;

      const nonce = await accountsStore.getCurrentNonce();

      const signed = await wallet.signTransaction({
        privateKey: accountsStore.currentPrivateKey,
        data,
        nonce,
        to,
      });

      const result = await rpcClient.sendTransaction(signed);
      transactionsStore.addTransaction({
        contractAddress: address.value || '',
        localContractId: contract.value?.id || '',
        hash: result,
        type: 'method',
        status: 'PENDING',
        data: {},
        decodedData: {
          functionName: method,
          args,
        },
      });
      return true;
    } catch (error) {
      throw new Error('Error writing to contract');
    }
  }

  return {
    contractSchemaQuery,
    contractAbiQuery,
    contract,
    isDeploying,
    isDeployed,
    address,

    deployContract,
    callReadMethod,
    callWriteMethod,

    mockContractSchema,
    isMock,
  };
}
