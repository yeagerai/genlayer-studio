<script setup lang="ts">
import TextInput from '../inputs/TextInput.vue';
import { useUniqueId } from '@/hooks';
import { AnyFieldValue } from './AnyFieldValue';
import FieldLabel from './FieldLabel.vue';

const fieldId = useUniqueId('anyField');

const props = defineProps<{
  name: string;
  label: string;
  testId?: string;
  placeholder?: string;
}>();

const model = defineModel({
  set(value) {
    console.assert(
      typeof value === 'string',
      `value typeof ${value} is ${typeof value} ${String(value)}`,
    );
    return new AnyFieldValue(value as string);
  },
});
</script>

<template>
  <div class="flex w-full flex-col">
    <FieldLabel :for="fieldId" tiny>{{ name }}</FieldLabel>
    <TextInput
      v-model="model"
      v-bind="props"
      :id="fieldId"
      :placeholder="props.placeholder"
      tiny
    />
  </div>
</template>
