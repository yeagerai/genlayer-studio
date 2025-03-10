<script setup lang="ts">
import {
  PresentationChartLineIcon,
  InboxArrowDownIcon,
} from '@heroicons/vue/24/solid';
import { SunIcon, MoonIcon } from '@heroicons/vue/16/solid';
import { useUIStore } from '@/stores';
import { RouterLink } from 'vue-router';
import Logo from '@/assets/images/logo.svg';
import GhostBtn from './global/GhostBtn.vue';
import AccountSelect from '@/components/Simulator/AccountSelect.vue';
import SimulatorMenuLink from './SimulatorMenuLink.vue';
import { ref } from 'vue';
import { RpcClient } from '@/clients/rpc.ts';
import type { JsonRPCRequest, JsonRPCResponse } from '@/types';

const rpcClient = new RpcClient();
const responseData = ref<JsonRPCResponse<any> | null>(null);
const showInputModal = ref(false);
const contractAddress = ref(''); // Store the input field value

function toggleInputModal() {
  console.log('toggleInputModal executed!');
  showInputModal.value = !showInputModal.value;
}

async function callRpcMethod(address) {
  try {
    const request: JsonRPCRequest = {
      method: 'gen_getContractByAddress',
      params: { address },
    };

    console.log('Sending RPC request:', request);
    const response = await rpcClient.call(request);
    responseData.value = response;
    console.log('RPC Response:', response);
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

const uiStore = useUIStore();

const toggleMode = () => {
  uiStore.toggleMode();
};

const showTutorial = () => {
  uiStore.runTutorial();
};
</script>

<template>
  <header
    class="flex items-center justify-between border-b border-b-slate-500 p-2 dark:border-b-zinc-500 dark:bg-zinc-800"
  >
    <RouterLink to="/">
      <Logo
        alt="GenLayer Logo"
        height="36"
        :class="[
          'block',
          uiStore.mode === 'light' ? 'text-primary' : 'text-white',
        ]"
      />
    </RouterLink>

    <div class="flex items-center gap-2 pr-2">
      <SimulatorMenuLink
        v-tooltip="{
          content: 'Import Contract from Address',
          placement: 'right',
        }"
        @click="
          () => {
            console.log('InboxArrowDownIcon clicked!');
            toggleInputModal();
          }
        "
      >
        <InboxArrowDownIcon />
      </SimulatorMenuLink>

      <AccountSelect />

      <GhostBtn @click="toggleMode" v-tooltip="'Switch theme'">
        <SunIcon v-if="uiStore.mode === 'light'" class="h-5 w-5" />
        <MoonIcon v-else class="h-5 w-5 fill-gray-200" />
      </GhostBtn>

      <GhostBtn
        @click="showTutorial"
        v-tooltip="'Show Tutorial'"
        id="tutorial-end"
      >
        <PresentationChartLineIcon
          class="h-5 w-5"
          :class="uiStore.mode === 'light' ? 'fill-gray-700' : 'fill-gray-200'"
        />
      </GhostBtn>
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
  </header>
</template>
