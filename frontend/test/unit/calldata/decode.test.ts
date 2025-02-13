import { describe, it, expect } from 'vitest';

import { abi } from 'genlayer-js';
import { parse as calldataParse } from '@/calldata/parser';
import { b64ToArray } from '@/calldata/jsonifier';

describe('calldata decoding tests', () => {
  it('smoke', () => {
    const bin_b64 =
      'DgF4PQAQCBgBAQEBAQEBAQEBAQEBAQEBAQEBAcwB0YDRg9GB0YHQutC40LUg0LHRg9C60LLRi1FK';
    const bin_text =
      'eyd4JzpbbnVsbCx0cnVlLGZhbHNlLGFkZHIjMDEwMTAxMDEwMTAxMDEwMTAxMDEwMTAxMDEwMTAxMDEwMTAxMDEwMSwn0YDRg9GB0YHQutC40LUg0LHRg9C60LLRiycsMTAsLTEwLF0sfQ==';

    const bin = b64ToArray(bin_b64);

    const text_decoded_to_arr = b64ToArray(bin_text);
    const text = new TextDecoder('utf-8').decode(text_decoded_to_arr);

    const parsed = calldataParse(text);
    const decoded = abi.calldata.decode(bin);
    expect(decoded).toEqual(parsed);
  });
});
