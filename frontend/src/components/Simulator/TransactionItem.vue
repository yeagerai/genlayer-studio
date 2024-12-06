<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { TransactionItem } from '@/types';
import TransactionStatusBadge from '@/components/Simulator/TransactionStatusBadge.vue';
import { useTimeAgo } from '@vueuse/core';
import ModalSection from '@/components/Simulator/ModalSection.vue';
import JsonViewer from '@/components/JsonViewer/json-viewer.vue';
import { useUIStore, useNodeStore, useTransactionsStore } from '@/stores';
import { CheckCircleIcon, XCircleIcon } from '@heroicons/vue/16/solid';
import CopyTextButton from '../global/CopyTextButton.vue';
import { FilterIcon } from 'lucide-vue-next';
import { GavelIcon } from 'lucide-vue-next';
import * as calldata from '@/calldata';

const uiStore = useUIStore();
const nodeStore = useNodeStore();
const transactionsStore = useTransactionsStore();

const props = defineProps<{
  transaction: TransactionItem;
}>();

const isDetailsModalOpen = ref(false);

const timeThreshold = 6; // Number of hours after which the date should be displayed instead of time ago

const dateText = computed(() => {
  const currentDate = Date.now(); // Get the current timestamp in milliseconds
  const transactionDate = new Date(props.transaction.data.created_at).getTime(); // Convert transaction date to a timestamp
  const twelveHoursInMilliseconds = timeThreshold * 60 * 60 * 1000;

  if (currentDate - transactionDate > twelveHoursInMilliseconds) {
    return new Date(transactionDate).toLocaleString(); // Return formatted date string
  } else {
    return useTimeAgo(transactionDate).value; // Return time ago string (e.g., "3 hours ago")
  }
});

const leaderReceipt = computed(() => {
  return props.transaction?.data?.consensus_data?.leader_receipt;
});

const shortHash = computed(() => {
  return props.transaction.hash?.slice(0, 6);
});

const isAppealed = ref(false);

const handleSetTransactionAppeal = () => {
  transactionsStore.setTransactionAppeal(props.transaction.hash);

  isAppealed.value = true;
};

watch(
  () => props.transaction.status,
  (newStatus) => {
    if (newStatus !== 'ACCEPTED') {
      isAppealed.value = false;
    }
  },
);

function prettifyTxData(x: any): any {
  const oldEqOutputs = x?.consensus_data?.leader_receipt?.eq_outputs;
  if (oldEqOutputs == undefined) {
    return x;
  }
  try {
    const new_eq_outputs = Object.fromEntries(
      Object.entries(oldEqOutputs).map(([k, v]) => {
        const val = Uint8Array.from(atob(v as string), (c) => c.charCodeAt(0));
        const rest = new Uint8Array(val).slice(1);
        if (val[0] == 0) {
          return [
            k,
            {
              status: 'success',
              data: calldata.toString(calldata.decode(rest)),
            },
          ];
        } else if (val[0] == 1) {
          return [
            k,
            { status: 'rollback', data: new TextDecoder('utf-8').decode(rest) },
          ];
        }
        return [k, v];
      }),
    );
    const ret = {
      ...x,
      consensus_data: {
        ...x.consensus_data,
        leader_receipt: {
          ...x.consensus_data.leader_receipt,
          eq_outputs: new_eq_outputs,
        },
      },
    };
    return ret;
  } catch (e) {
    console.log(e);
    return x;
  }
}
</script>

<template>
  <div
    class="group flex cursor-pointer flex-row items-center justify-between gap-2 rounded p-0.5 pl-1 hover:bg-gray-100 dark:hover:bg-zinc-700"
    @click="isDetailsModalOpen = true"
  >
    <div class="flex flex-row text-xs text-gray-500 dark:text-gray-400">
      <span class="font-mono">{{ shortHash }}</span>
      <span class="font-normal">...</span>
    </div>

    <div class="grow truncate text-left text-[11px] font-medium">
      {{
        transaction.type === 'method'
          ? transaction.decodedData?.functionName
          : 'Deploy'
      }}
    </div>

    <div class="hidden flex-row items-center gap-1 group-hover:flex">
      <CopyTextButton
        :text="transaction.hash"
        v-tooltip="'Copy transaction hash'"
        class="h-4 w-4"
      />

      <button
        @click.stop="nodeStore.searchFilter = transaction.hash"
        class="active:scale-90"
      >
        <FilterIcon
          v-tooltip="'Filter logs by hash'"
          class="h-4 w-4 text-gray-400 outline-none transition-all hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400"
        />
      </button>
    </div>

    <div class="flex items-center justify-between gap-2 p-1">
      <Loader :size="15" v-if="transaction.status !== 'FINALIZED'" />

      <!-- <TransactionStatusBadge
        as="button"
        @click.stop="handleSetTransactionAppeal"
        :class="{ '!bg-green-500': isAppealed }"
        v-if="transaction.status == 'ACCEPTED'"
        v-tooltip="'Appeal transaction'"
      >
        <div class="flex items-center gap-1">
          APPEAL
          <GavelIcon class="h-3 w-3" />
        </div>
      </TransactionStatusBadge> -->

      <TransactionStatusBadge class="px-[4px] py-[1px] text-[9px]">
        {{ transaction.status }}
      </TransactionStatusBadge>
    </div>

    <Modal :open="isDetailsModalOpen" @close="isDetailsModalOpen = false" wide>
      <template #title>
        <div class="flex flex-row items-center justify-between gap-2">
          <div>
            Transaction
            <span class="text-sm font-medium text-gray-400">
              {{
                transaction.type === 'method'
                  ? 'Method Call'
                  : 'Contract Deployment'
              }}
            </span>
          </div>

          <span class="text-[12px]">
            {{ dateText }}
          </span>
        </div>
      </template>

      <template #info>
        <div
          class="flex flex-row items-center justify-center gap-2 text-xs font-normal"
        >
          {{ transaction.hash }}
          <CopyTextButton :text="transaction.hash" />
        </div>
      </template>

      <div class="flex flex-col gap-4">
        <div class="mt-2 flex flex-col">
          <p
            class="text-md mb-1 flex flex-row items-center gap-2 font-semibold"
          >
            Status:
            <Loader :size="15" v-if="transaction.status !== 'FINALIZED'" />
            <TransactionStatusBadge>
              {{ transaction.status }}
            </TransactionStatusBadge>
          </p>
        </div>

        <ModalSection v-if="transaction.data.data">
          <template #title>Input</template>

          <pre
            class="overflow-hidden rounded bg-gray-200 p-1 text-xs text-gray-600 dark:bg-zinc-800 dark:text-gray-300"
            >{{ transaction.data.data }}</pre
          >
        </ModalSection>

        <ModalSection v-if="leaderReceipt">
          <template #title>
            Execution
            <TransactionStatusBadge
              :class="
                leaderReceipt.execution_result === 'ERROR'
                  ? '!bg-red-500'
                  : '!bg-green-500'
              "
            >
              {{ leaderReceipt.execution_result }}
            </TransactionStatusBadge>
          </template>

          <span class="text-sm font-semibold">Leader:</span>

          <div class="flex flex-row items-start gap-4 text-xs">
            <div>
              <div>
                <span class="font-medium">Gas used:</span>
                {{ leaderReceipt.gas_used }}
              </div>
              <div>
                <span class="font-medium"
                  >Stake: {{ leaderReceipt.node_config.stake }}</span
                >
              </div>
            </div>

            <div>
              <div>
                <span class="font-medium">Model:</span>
                {{ leaderReceipt.node_config.model }}
              </div>
              <div>
                <span class="font-medium">Provider:</span>
                {{ leaderReceipt.node_config.provider }}
              </div>
            </div>
          </div>
        </ModalSection>

        <ModalSection v-if="transaction.data.consensus_data">
          <template #title>Validators</template>

          <div
            class="divide-y overflow-hidden rounded border dark:border-gray-600"
          >
            <div
              class="flex flex-row items-center justify-between p-2 text-xs font-semibold dark:border-gray-600"
            >
              <div>Address</div>
              <div>Vote</div>
            </div>

            <div
              v-for="(vote, address) in transaction.data.consensus_data.votes"
              :key="address"
              class="flex flex-row items-center justify-between p-2 text-xs dark:border-gray-600"
            >
              <div class="font-mono text-xs">
                {{ address }}
              </div>

              <div class="flex flex-row items-center gap-1 capitalize">
                <template v-if="vote === 'agree'">
                  <CheckCircleIcon class="h-4 w-4 text-green-500" />
                  Agree
                </template>

                <template v-if="vote === 'disagree'">
                  <XCircleIcon class="h-4 w-4 text-red-500" />
                  Disagree
                </template>
              </div>
            </div>
          </div>
        </ModalSection>

        <ModalSection v-if="leaderReceipt?.eq_outputs?.leader">
          <template #title>Equivalence Principle Output</template>

          <pre
            class="overflow-x-auto rounded bg-gray-200 p-1 text-xs text-gray-600 dark:bg-zinc-800 dark:text-gray-300"
            >{{ leaderReceipt?.eq_outputs?.leader }}</pre
          >
        </ModalSection>

        <ModalSection v-if="transaction.data">
          <template #title>Full Transaction Data</template>

          <JsonViewer
            class="overflow-y-auto rounded-md bg-white p-2 dark:bg-zinc-800"
            :value="prettifyTxData(transaction.data || {})"
            :theme="uiStore.mode === 'light' ? 'light' : 'dark'"
            :expand="true"
            sort
          />
        </ModalSection>
      </div>
    </Modal>
  </div>
</template>
