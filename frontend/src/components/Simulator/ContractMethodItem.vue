<script setup lang="ts">
import type { ContractMethod } from 'genlayer-js/types';
import { abi } from 'genlayer-js';
import { ref } from 'vue';
import { Collapse } from 'vue-collapsed';
import { notify } from '@kyvg/vue3-notification';
import { ChevronDownIcon } from '@heroicons/vue/16/solid';
import { useEventTracking, useContractQueries } from '@/hooks';
import { unfoldArgsData, type ArgData } from './ContractParams';
import ContractParams from './ContractParams.vue';

const { callWriteMethod, callReadMethod, contract } = useContractQueries();
const { trackEvent } = useEventTracking();

const props = defineProps<{
  name: string;
  method: ContractMethod;
  methodType: 'read' | 'write';
  leaderOnly: boolean;
}>();

const isExpanded = ref(false);
const isCalling = ref(false);
const responseMessage = ref();

const calldataArguments = ref<ArgData>({ args: [], kwargs: {} });

const formatResponseIfNeeded = (response: string): string => {
  // Check if the string looks like a malformed JSON (starts with { and ends with })
  if (response.startsWith('{') && response.endsWith('}')) {
    try {
      // Try to parse it as-is first
      return JSON.stringify(JSON.parse(response), null, 2);
    } catch {
      // If parsing fails, try to add commas between properties
      const fixedResponse = response.replace(/"\s*"(?=[^:]*:)/g, '","');
      try {
        // Validate the fixed string can be parsed as JSON
        return JSON.stringify(JSON.parse(fixedResponse), null, 2);
      } catch {
        // If still can't parse, return original
        return response;
      }
    }
  }
  return response;
};

const handleCallReadMethod = async () => {
  isCalling.value = true;

  try {
    const result = await callReadMethod(
      props.name,
      unfoldArgsData(calldataArguments.value),
    );

    if (result !== undefined) {
      const resultString = abi.calldata.toString(result);
      responseMessage.value = formatResponseIfNeeded(resultString);
    } else {
      responseMessage.value = '<genlayer.client is undefined>';
    }

    trackEvent('called_read_method', {
      contract_name: contract.value?.name || '',
      method_name: props.name,
    });
  } catch (error) {
    notify({
      title: 'Error',
      text: (error as Error)?.message || 'Error getting contract state',
      type: 'error',
    });
  } finally {
    isCalling.value = false;
  }
};

const handleCallWriteMethod = async () => {
  isCalling.value = true;

  try {
    await callWriteMethod({
      method: props.name,
      leaderOnly: props.leaderOnly,
      args: unfoldArgsData({
        args: calldataArguments.value.args,
        kwargs: calldataArguments.value.kwargs,
      }),
    });

    notify({
      text: 'Write method called',
      type: 'success',
    });

    trackEvent('called_write_method', {
      contract_name: contract.value?.name || '',
      method_name: props.name,
    });
  } catch (error) {
    notify({
      title: 'Error',
      text: (error as Error)?.message || 'Error getting contract state',
      type: 'error',
    });
  } finally {
    isCalling.value = false;
  }
};
</script>

<template>
  <div
    class="dark:bg-g flex flex-col overflow-hidden rounded-md bg-slate-100 dark:bg-gray-700"
  >
    <button
      class="flex grow flex-row items-center justify-between bg-slate-200 p-2 text-xs hover:bg-slate-300 dark:bg-slate-600 dark:hover:bg-slate-500"
      @click="isExpanded = !isExpanded"
      :data-testid="`expand-method-btn-${name}`"
    >
      <div class="truncate">
        {{ name }}
      </div>

      <ChevronDownIcon
        class="h-4 w-4 opacity-70 transition-all duration-300"
        :class="isExpanded && 'rotate-180'"
      />
    </button>

    <Collapse :when="isExpanded">
      <div class="flex flex-col items-start gap-2 p-2">
        <ContractParams
          :methodBase="props.method"
          @argsChanged="
            (v: ArgData) => {
              calldataArguments = v;
            }
          "
        />

        <div>
          <Btn
            v-if="methodType === 'read'"
            @click="handleCallReadMethod"
            tiny
            :data-testid="`read-method-btn-${name}`"
            :loading="isCalling"
            :disabled="isCalling"
            >{{ isCalling ? 'Calling...' : 'Call Contract' }}</Btn
          >

          <Btn
            v-if="methodType === 'write'"
            @click="handleCallWriteMethod"
            tiny
            :data-testid="`write-method-btn-${name}`"
            :loading="isCalling"
            :disabled="isCalling"
            >{{ isCalling ? 'Sending...' : 'Send Transaction' }}</Btn
          >
        </div>

        <div v-if="responseMessage" class="w-full break-all text-sm">
          <div class="mb-1 text-xs font-medium">Response:</div>
          <div
            :data-testid="`method-response-${name}`"
            class="w-full whitespace-pre-wrap rounded bg-white p-1 font-mono text-xs dark:bg-slate-600"
          >
            {{ responseMessage }}
          </div>
        </div>
      </div>
    </Collapse>
  </div>
</template>
