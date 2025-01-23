import { describe, it, expect } from 'vitest';

import { abi } from 'genlayer-js';
import { CalldataAddress } from 'genlayer-js/types';
import { parse as calldataParse } from '@/calldata/parser';

describe('calldata parsing tests', () => {
  it('string escapes', () => {
    expect(calldataParse('"\\n"')).toEqual('\n');
    expect(calldataParse('"\\r"')).toEqual('\r');
    expect(calldataParse('"\\t"')).toEqual('\t');
    expect(calldataParse('"\\u00029e3d"')).toEqual('𩸽');
  });
  it('numbers', () => {
    expect(calldataParse('0')).toEqual(0n);
    expect(calldataParse('0xff')).toEqual(0xffn);
    expect(calldataParse('0o77')).toEqual(0o77n);
  });

  it('numbers + sign', () => {
    expect(calldataParse('+0')).toEqual(0n);
    expect(calldataParse('+0xff')).toEqual(0xffn);
    expect(calldataParse('+0o77')).toEqual(0o77n);
  });

  it('numbers - sign', () => {
    expect(calldataParse('-0')).toEqual(-0n);
    expect(calldataParse('-0xff')).toEqual(-0xffn);
    expect(calldataParse('-0o77')).toEqual(-0o77n);
  });

  it('all types', () => {
    const asStr = `{
            'true': true,
            'false': false,
            'null': null,
            str: '123',
            str2: "abc",
            num: 0xf,
            bytes: b#dead,
            addr: addr#0000000000000000000000000000000000000000,
            arr: [-2, -0o7, -0xff00, -0]
        }`;
    const asLiteral = {
      true: true,
      false: false,
      null: null,
      str: '123',
      str2: 'abc',
      num: 0xf,
      bytes: new Uint8Array([0xde, 0xad]),
      addr: new CalldataAddress(new Uint8Array(new Array(20).map(() => 0))),
      arr: [-2, -0o7, -0xff00, -0],
    };

    expect(abi.calldata.encode(calldataParse(asStr))).toEqual(
      abi.calldata.encode(asLiteral),
    );
  });

  it('trailing comma', () => {
    const asStr = `
        {
            a: {},
            b: {x: 2,},
            c: [],
            d: [1,],
        }`;
    const asLit = {
      a: {},
      b: { x: 2 },
      c: [],
      d: [1],
    };
    expect(abi.calldata.encode(calldataParse(asStr))).toEqual(
      abi.calldata.encode(asLit),
    );
  });

  it('string escapes', () => {
    expect(calldataParse('"\\\\"')).toEqual('\\');
    expect(calldataParse('"\\n"')).toEqual('\n');

    expect(() => calldataParse('"\\a"')).toThrow();
  });

  it('errors', () => {
    expect(() => calldataParse('b#1')).toThrow();
    expect(() => calldataParse('0xz')).toThrow();
    expect(() => calldataParse('0o8')).toThrow();
    expect(() => calldataParse('addr#1234')).toThrow();
  });
});
