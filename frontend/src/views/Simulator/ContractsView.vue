<script setup lang="ts">
import { useContractsStore } from '@/stores';
import { FilePlus2, Upload } from 'lucide-vue-next';
import { ref } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import ContractItem from '@/components/Simulator/ContractItem.vue';
import MainTitle from '@/components/Simulator/MainTitle.vue';
import { useEventTracking } from '@/hooks';
import { InboxArrowDownIcon } from '@heroicons/vue/24/solid';
import { RpcClient } from '@/clients/rpc.ts';
import type { JsonRPCRequest, JsonRPCResponse } from '@/types';

const rpcClient = new RpcClient();
const responseData = ref<JsonRPCResponse<any> | null>(null);
const showInputModal = ref(false);
const contractAddress = ref(''); // Store the input field value

function toggleInputModal() {
  showInputModal.value = !showInputModal.value;
}

async function callRpcMethod(address: string) {
  try {
    const request: JsonRPCRequest = {
      method: 'gen_getContractByAddress',
      params: [address],
    };

    const response = await rpcClient.call(request);
    responseData.value = response;

    if (response.result) {
      const id = uuidv4();
      const content = (
        response.result as { contract_code: string }
      ).contract_code
        .replace(/^b'/, '') // Remove b' prefix
        .replace(/'$/, '') // Remove trailing '
        .replace(/\\n/g, '\n') // Convert \n to actual newlines
        .replace(/\\t/g, '\t') // Convert \t to actual tabs
        .replace(/\\"/g, '"') // Convert \" to actual quotes
        .replace(/\\\\/g, '\\'); // Convert \\ to actual backslashes

      store.addContractFile({
        id,
        name: `contract_${address.slice(0, 8)}.gpy`,
        content,
      });
      store.openFile(id);
      toggleInputModal(); // Close the modal after successful import
    }
  } catch (error) {
    console.error('RPC Call Failed:', error);
  }
}

function importContract() {
  if (!contractAddress.value.trim()) {
    console.error('Please enter a valid contract address');
    return;
  }
  callRpcMethod(contractAddress.value);
}

const store = useContractsStore();
const showNewFileInput = ref(false);
const { trackEvent } = useEventTracking();

/**
 * Loads content from a file and adds it to the contract file store.
 *
 * @param {Event} event - The event triggered by the file input element.
 */
const loadContentFromFile = (event: Event) => {
  const target = event.target as HTMLInputElement;

  if (target.files && target.files.length > 0) {
    const [file] = target.files;
    const reader = new FileReader();

    reader.onload = (ev: ProgressEvent<FileReader>) => {
      if (ev.target?.result) {
        const id = uuidv4();
        store.addContractFile({
          id,
          name: file.name,
          content: (ev.target?.result as string) || '',
        });
        store.openFile(id);
      }
    };

    reader.readAsText(file);
  }
};

const handleAddNewFile = () => {
  if (!showNewFileInput.value) {
    showNewFileInput.value = true;
  }
};

const handleSaveNewFile = (name: string) => {
  if (name && name.replace('.gpy', '') !== '') {
    const id = uuidv4();
    store.addContractFile({ id, name, content: '' });
    store.openFile(id);

    trackEvent('created_contract', {
      contract_name: name,
    });
  }

  showNewFileInput.value = false;
};
</script>

<template>
  <div class="flex w-full flex-col">
    <MainTitle data-testid="contracts-page-title">
      Your Contracts

      <template #actions>
        <GhostBtn @click="handleAddNewFile" v-tooltip="'New Contract'">
          <FilePlus2 :size="16" />
        </GhostBtn>

        <GhostBtn class="!p-0" v-tooltip="'Add From File'">
          <label class="input-label p-1">
            <input
              type="file"
              @change="loadContentFromFile"
              accept=".gpy,.py"
            />
            <Upload :size="16" />
          </label>
        </GhostBtn>

        <GhostBtn
          v-tooltip="'Import Contract from Address'"
          @click="toggleInputModal"
        >
          <InboxArrowDownIcon class="h-4 w-4" />
        </GhostBtn>
      </template>
    </MainTitle>

    <div id="tutorial-how-to-change-example">
      <ContractItem
        @click="store.openFile(contract.id)"
        v-for="contract in store.contractsOrderedByName"
        :key="contract.id"
        :contract="contract"
        :isActive="contract.id === store.currentContractId"
      />
    </div>

    <ContractItem
      v-if="showNewFileInput"
      :isNewFile="true"
      @save="handleSaveNewFile"
      @cancel="showNewFileInput = false"
    />
  </div>

  <!-- Modal -->
  <div
    v-if="showInputModal"
    class="fixed inset-0 z-[9999] flex items-center justify-center bg-black bg-opacity-50"
  >
    <div class="relative z-[10000] w-96 rounded-lg bg-white p-6 shadow-lg">
      <h2 class="mb-4 text-lg font-semibold">Import Contract</h2>
      <input
        type="text"
        v-model="contractAddress"
        class="w-full rounded-md border p-2"
        placeholder="Enter contract address"
      />

      <!-- Button Row -->
      <div class="mt-4 flex justify-end space-x-3">
        <button
          @click="toggleInputModal"
          class="rounded-md bg-gray-300 px-4 py-2 text-gray-700"
        >
          Cancel
        </button>
        <button
          @click="importContract"
          class="rounded-md bg-green-500 px-4 py-2 text-white"
        >
          Import
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-label {
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.input-label input {
  position: absolute;
  top: 0;
  left: 0;
  z-index: -1;
  opacity: 0;
}
</style>
