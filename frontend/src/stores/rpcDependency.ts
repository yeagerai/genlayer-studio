import { ref } from 'vue';
import { RpcClient } from '@/clients/rpc';
import { JsonRpcService } from '@/services/JsonRpcService';

const rpcClient = new JsonRpcService(new RpcClient());

export const useRpcDependencyStore = () => {
  return {
    rpcClient: ref(rpcClient),
  };
};
