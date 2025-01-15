import { describe, it, expect } from 'vitest';
import { useInputMap } from '@/hooks';
import StringField from '@/components/global/fields/StringField.vue';
import IntegerField from '@/components/global/fields/IntegerField.vue';
import BooleanField from '@/components/global/fields/BooleanField.vue';
import AnyField from '@/components/global/fields/AnyField.vue';

describe('useInputMap composable', () => {
  const { getComponent } = useInputMap();

  it('should return the correct component for type "string"', () => {
    const component = getComponent('string');
    expect(component).toBe(StringField);
  });

  it('should return the correct component for type "int"', () => {
    const component = getComponent('int');
    expect(component).toBe(IntegerField);
  });

  it('should return the correct component for type "bool"', () => {
    const component = getComponent('bool');
    expect(component).toBe(BooleanField);
  });

  it('should default to string for an empty type', () => {
    const component = getComponent('' as any);
    expect(component).toBe(AnyField);
  });

  it('should default to string for an unknown type', () => {
    const component = getComponent('unknown' as any);
    expect(component).toBe(AnyField);
  });
});
