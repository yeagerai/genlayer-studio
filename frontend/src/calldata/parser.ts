/// This file introduces text format for calldata. It is quite similar to json, but has two more types: bytes and addresses
/// Literals: null, true, false
/// Numbers: 0, 0xff, 0o77, 89, -11 (integers of arbitrary size)
/// Strings: "double quote", 'single quote', they support escapes: '\\', '\n', '\r', '\"', '\"'
///   all strings must be valid (no unpaired surrogates, as js is utf16)
/// Bytes: b#00ff (hex encoded, no quotes)
/// Address: addr#3030303030303030303030303030303030303030303030303030303030303030 (32 bytes)
/// Arrays: [], ['x'], ['trailing',]
/// Maps: {}, { lit: 123 }, { "str": 456 }
/// After encoding strings will be encoded as utf8, Map keys will be sorted

/// More complex examples (left is js ;; right is calldata-str)
/// new Uint8Array([0xff]) ;; b#ff
/// 1n ;; 1
/// -1n ;; -1
/// "123" ;; "123"
/// { "a": 123 } ;; { "a": 123 }

import type { Token, Parser } from 'typescript-parsec';
import {
  buildLexer,
  expectEOF,
  expectSingleResult,
  rule,
} from 'typescript-parsec';
import {
  alt,
  apply,
  kleft,
  kright,
  list,
  seq,
  tok,
  opt,
} from 'typescript-parsec';

import { CalldataAddress, type CalldataEncodable } from 'genlayer-js/types';

enum TokenKind {
  Atom,
  Number,
  Str,
  Bytes,
  Addr,
  LCpar,
  RCpar,
  LSpar,
  RSpar,
  Comma,
  Colon,
  Id,
  Skip,
}
const lexer = buildLexer([
  [false, /^\s+/g, TokenKind.Skip],
  [false, /^\/\/[^\n]*/g, TokenKind.Skip],

  [true, /^[-+]?(?:(?:0x[a-fA-F0-9]+)|(?:0o\d+)|\d+)/g, TokenKind.Number],
  [true, /^(?:true|false|null)/g, TokenKind.Atom],
  [true, /^addr#[a-fA-F0-9]+/g, TokenKind.Addr],
  [true, /^b#[a-fA-F0-9]*/g, TokenKind.Bytes],
  [true, /^\{/g, TokenKind.LCpar],
  [true, /^\[/g, TokenKind.LSpar],
  [true, /^\}/g, TokenKind.RCpar],
  [true, /^\]/g, TokenKind.RSpar],
  [true, /^,/g, TokenKind.Comma],
  [true, /^:/g, TokenKind.Colon],
  [true, /^(?!\d)\w\w*/g, TokenKind.Id],
  [true, /^'(?:[^'\\]|\\.)*'/g, TokenKind.Str],
  [true, /^"(?:[^"\\]|\\.)*"/g, TokenKind.Str],
]);

const ATOMS = new Map([
  ['null', null],
  ['false', false],
  ['true', true],
]);

function parseNumber(n: string, base: bigint): bigint {
  const bn = Number(base);
  const alphabet = '0123456789ABCDEF';
  return Array.prototype.reduce.call(
    n,
    (acc: any, digit) => {
      const pos = BigInt(alphabet.indexOf(digit.toUpperCase()));
      if (pos >= bn || pos < 0) {
        throw new Error(
          `digit ${digit} (code point 0x${digit.codePointAt(0).toString(16)}) is out of range for base ${base}`,
        );
      }
      return acc * base + pos;
    },
    0n,
  ) as bigint;
}

function parseHex(text: string): Uint8Array {
  if (text.length % 2 != 0) {
    throw new Error('invalid hex length');
  }
  const res: number[] = [];
  for (let i = 0; i < text.length; i += 2) {
    res.push(parseInt(text.substring(i, i + 2), 16));
  }
  return new Uint8Array(res);
}

function applyNumber(n: Token<TokenKind.Number>) {
  const txtSign = n.text;
  let txtNoSign: string;
  let sign = 1n;
  if (txtSign.startsWith('-')) {
    txtNoSign = txtSign.substring(1);
    sign = -1n;
  } else if (txtSign.startsWith('+')) {
    txtNoSign = txtSign.substring(1);
  } else {
    txtNoSign = txtSign;
  }

  if (txtNoSign.startsWith('0x')) {
    return parseNumber(txtNoSign.substring(2), 16n) * sign;
  }
  if (txtNoSign.startsWith('0o')) {
    return parseNumber(txtNoSign.substring(2), 8n) * sign;
  }
  return parseNumber(txtNoSign, 10n) * sign;
}

function applyString(n: Token<TokenKind.Str>): string {
  const txt = n.text.substring(1, n.text.length - 1);
  return txt.replaceAll(/\\(?:u........|[^u])/g, (str) => {
    if (str.startsWith('\\u')) {
      const code = parseInt(str.substring(2), 16);
      return String.fromCodePoint(code);
    }
    switch (str) {
      case '\\\\':
        return '\\';
      case "\\'":
        return "'";
      case '\\"':
        return '"';
      case '\\n':
        return '\n';
      case '\\t':
        return '\t';
      case '\\r':
        return '\r';
      default:
        throw new Error(`unsupported escape code ${str}`);
    }
  });
}

/// unites all non-recursive non-terminals
const TERM = rule<TokenKind, CalldataEncodable>();
const ARR = rule<TokenKind, Array<CalldataEncodable>>();
const MAP = rule<TokenKind, Map<string, CalldataEncodable>>();
/// any valid calldata
const EXPR = rule<TokenKind, CalldataEncodable>();

const FETCH_STR = rule<TokenKind, string>();
FETCH_STR.setPattern(apply(tok(TokenKind.Str), applyString));

TERM.setPattern(
  alt(
    apply(tok(TokenKind.Atom), (v) => ATOMS.get(v.text) as CalldataEncodable),
    FETCH_STR,
    apply(tok(TokenKind.Number), applyNumber),
    apply(tok(TokenKind.Bytes), (v) => parseHex(v.text.substring(2))),
    apply(
      tok(TokenKind.Addr),
      (v) => new CalldataAddress(parseHex(v.text.substring(5))),
    ),
  ),
);

ARR.setPattern(
  parseArray(
    tok(TokenKind.LSpar),
    EXPR,
    tok(TokenKind.Comma),
    tok(TokenKind.RSpar),
  ),
);

function parseArray<TKind, TRes, T1, T2, T3>(
  left: Parser<TKind, T1>,
  elem: Parser<TKind, TRes>,
  sep: Parser<TKind, T2>,
  right: Parser<TKind, T3>,
): Parser<TKind, TRes[]> {
  return kright(
    left,
    alt(
      apply(right, () => []),
      kleft(list(elem, sep), seq(opt(sep), right)),
    ),
  );
}

const ARR_ID = rule<TokenKind, string>();
ARR_ID.setPattern(
  alt(
    FETCH_STR,
    apply(tok(TokenKind.Id), (v) => v.text),
  ),
);

MAP.setPattern(
  apply(
    parseArray(
      tok(TokenKind.LCpar),
      apply(
        seq(ARR_ID, tok(TokenKind.Colon), EXPR),
        (x): [string, CalldataEncodable] => [x[0], x[2]],
      ),
      tok(TokenKind.Comma),
      tok(TokenKind.RCpar),
    ),
    (v) => new Map(v),
  ),
);

EXPR.setPattern(alt(TERM, ARR, MAP));

export function parse(s: string): CalldataEncodable {
  return expectSingleResult(expectEOF(EXPR.parse(lexer.parse(s))));
}
