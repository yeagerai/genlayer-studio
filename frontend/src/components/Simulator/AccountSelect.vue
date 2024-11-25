<script setup>
import { useAccountsStore } from '@/stores';
import AccountItem from '@/components/Simulator/AccountItem.vue';
import { Dropdown } from 'floating-vue';
import { Wallet } from 'lucide-vue-next';
import { PlusIcon } from '@heroicons/vue/16/solid';
import { notify } from '@kyvg/vue3-notification';
import { useEventTracking } from '@/hooks';
import { createAccount } from 'genlayer-js';
const store = useAccountsStore();
const { trackEvent } = useEventTracking();

const handleCreateNewAccount = async () => {
  const privateKey = store.generateNewAccount();

  if (privateKey) {
    notify({
      title: 'New Account Created',
      type: 'success',
    });

    trackEvent('created_account');
  } else {
    notify({
      title: 'Error creating a new account',
      type: 'error',
    });
  }
};
</script>

<template>
  <Dropdown placement="bottom-end">
    <GhostBtn v-tooltip="'Switch account'">
      <Wallet class="h-5 w-5" />
      {{ store.displayAddress }}
    </GhostBtn>

    <template #popper>
      <div class="divide-y divide-gray-200 dark:divide-gray-800">
        <AccountItem
          v-for="privateKey in store.privateKeys"
          :key="privateKey"
          :privateKey="privateKey"
          :account="createAccount(privateKey)"
          :active="privateKey === store.currentPrivateKey"
          :canDelete="true"
          v-close-popper
        />
      </div>

      <div
        class="flex w-full border-t border-gray-300 bg-gray-200 p-1 dark:border-gray-600 dark:bg-gray-800"
      >
        <Btn
          @click="handleCreateNewAccount"
          secondary
          class="w-full"
          :icon="PlusIcon"
          >New account</Btn
        >
      </div>
    </template>
  </Dropdown>
</template>
