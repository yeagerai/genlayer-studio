import { abi } from 'genlayer-js';

export function b64ToArray(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64 as string), (c) => c.charCodeAt(0));
}

export function calldataToUserFriendlyJson(cd: Uint8Array): any {
  return {
    raw: Array.from(cd),
    readable: abi.calldata.toString(abi.calldata.decode(cd)),
  };
}

const RESULT_CODES = new Map([
  [0, 'return'],
  [1, 'rollback'],
  [2, 'contract_error'],
  [3, 'error'],
  [4, 'none'],
  [5, 'no_leaders'],
]);

export function resultToUserFriendlyJson(cd64: string): any {
  const raw = b64ToArray(cd64);

  const code = RESULT_CODES.get(raw[0]);
  let status: string;
  let payload: string | null = null;

  if (code === undefined) {
    status = '<unknown>';
  } else {
    status = code;
    if ([1, 2].includes(raw[0])) {
      payload = new TextDecoder('utf-8').decode(raw.slice(1));
    } else if (raw[0] == 0) {
      payload = calldataToUserFriendlyJson(raw.slice(1));
    }
  }

  return {
    raw: cd64,
    status,
    payload,
  };
}
