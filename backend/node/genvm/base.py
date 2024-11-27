# backend/node/genvm/base.py

__all__ = ("IGenVM", "GenVMHost")

import typing
import tempfile
from pathlib import Path
import shutil
import json
import base64
import asyncio
import socket
import backend.node.genvm.origin.base_host as genvmhost
import collections.abc
import functools
import traceback

from backend.node.types import (
    PendingTransaction,
    Address,
)
import backend.node.genvm.origin.calldata as calldata
from dataclasses import dataclass

from backend.node.genvm.config import get_genvm_path


# Unexpected error
# - user contract crushed (for instance from integer division by zero)
# - user contract is not a contract (genvm can't run it)
# - os-level error occurred (i.e. socket to genvm got closed)
@dataclass
class ExecutionFail:
    exc: list[Exception]

    def __repr__(self) -> str:
        lines: list[str] = ["ExecutionFail:\n"]
        for exc_lines in (traceback.format_exception(e) for e in self.exc):
            lines.extend(exc_lines)
        return "".join(lines)


@dataclass
class ExecutionReturn:
    ret: bytes


# Expected contract error (i.e. handled invalid arguments)
@dataclass
class ExecutionRollback:
    message: str


@dataclass
class ExecutionResult:
    result: ExecutionReturn | ExecutionRollback | ExecutionFail
    eq_outputs: dict[int, bytes]
    pending_transactions: list[PendingTransaction]
    stdout: str
    stderr: str
    genvm_log: str


# Interface for accessing the blockchain state, it is needed to not tangle current (awfully unoptimized)
# storage format with the genvm source code
class StateProxy(typing.Protocol):
    def storage_read(
        self, account: Address, slot: bytes, index: int, le: int, /
    ) -> bytes: ...
    def storage_write(
        self,
        account: Address,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None: ...
    def get_code(self, addr: Address) -> bytes: ...


# GenVM protocol just in case it is needed for mocks or bringing back the old one
class IGenVM(typing.Protocol):
    async def run_contract(
        self,
        state: StateProxy,
        *,
        from_address: Address,
        contract_address: Address,
        calldata_raw: bytes,
        is_init: bool = False,
        leader_results: None | dict[int, bytes],
        config: str,
    ) -> ExecutionResult: ...

    async def get_contract_schema(self, contract_code: bytes) -> ExecutionResult: ...


# state proxy that always fails and can give code only for address from a constructor
# useful for get_schema
class _StateProxyNone(StateProxy):
    def __init__(self, my_address: Address, code: bytes):
        self.my_address = my_address
        self.code = code

    def storage_read(
        self, account: Address, slot: bytes, index: int, le: int, /
    ) -> bytes:
        assert False

    def storage_write(
        self,
        account: Address,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None:
        assert False

    def get_code(self, addr: Address) -> bytes:
        assert addr == self.my_address
        return self.code


# Actual genvm wrapper that will start process and handle all communication
class GenVMHost(IGenVM):
    async def run_contract(
        self,
        state: StateProxy,
        *,
        from_address: Address,
        contract_address: Address,
        calldata_raw: bytes,
        is_init: bool = False,
        leader_results: None | dict[int, bytes],
        config: str,
    ) -> ExecutionResult:
        message = {
            "is_init": is_init,
            "contract_account": contract_address.as_b64,
            "sender_account": from_address.as_b64,
            "value": None,
            "gas": 2**64 - 1,
        }
        return await _run_genvm_host(
            functools.partial(
                _Host,
                calldata_bytes=calldata_raw,
                state_proxy=state,
                leader_results=leader_results,
            ),
            ["--message", json.dumps(message)],
            config,
        )

    async def get_contract_schema(self, contract_code: bytes) -> ExecutionResult:
        NO_ADDR = str(base64.b64encode(b"\x00" * 20), encoding="ascii")
        message = {
            "is_init": False,
            "contract_account": NO_ADDR,
            "sender_account": NO_ADDR,
            "value": None,
            "gas": 2**64 - 1,
        }
        return await _run_genvm_host(
            functools.partial(
                _Host,
                calldata_bytes=calldata.encode({"method": "__get_schema__"}),
                state_proxy=_StateProxyNone(Address(NO_ADDR), contract_code),
                leader_results=None,
            ),
            ["--message", json.dumps(message)],
            None,
        )


# Class that has logic for handling all genvm host methods and accumulating results
class _Host(genvmhost.IHost):
    _result: ExecutionReturn | ExecutionRollback | ExecutionFail | None
    _eq_outputs: dict[int, bytes]
    _pending_transactions: list[PendingTransaction]

    def __init__(
        self,
        sock_listen: socket.socket,
        *,
        calldata_bytes: bytes,
        state_proxy: StateProxy,
        leader_results: None | dict[int, bytes],
    ):
        self._eq_outputs = {}
        self._pending_transactions = []
        self._result = None

        self.sock_listen = sock_listen
        self.sock = None
        self._state_proxy = state_proxy
        self.calldata_bytes = calldata_bytes
        self._leader_results = leader_results

    def provide_result(
        self, res: genvmhost.RunHostAndProgramRes, fail: ExecutionFail | None
    ) -> ExecutionResult:
        ret = functools.partial(
            ExecutionResult,
            eq_outputs=self._eq_outputs,
            pending_transactions=self._pending_transactions,
            stdout=res.stdout,
            stderr=res.stderr,
            genvm_log=res.genvm_log,
        )
        if fail is not None:
            return ret(fail)
        if self._result is not None:
            return ret(self._result)
        return ret(ExecutionFail(exc=res.exceptions))

    async def loop_enter(self) -> socket.socket:
        async_loop = asyncio.get_event_loop()
        self.sock, _addr = await async_loop.sock_accept(self.sock_listen)
        self.sock.setblocking(False)
        self.sock_listen.close()
        return self.sock

    async def get_calldata(self, /) -> bytes:
        return self.calldata_bytes

    async def get_code(self, addr: bytes, /) -> bytes:
        return self._state_proxy.get_code(Address(addr))

    async def storage_read(
        self, account: bytes, slot: bytes, index: int, le: int, /
    ) -> bytes:
        return self._state_proxy.storage_read(Address(account), slot, index, le)

    async def storage_write(
        self,
        account: bytes,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None:
        return self._state_proxy.storage_write(Address(account), slot, index, got)

    async def consume_result(
        self, type: genvmhost.ResultCode, data: collections.abc.Buffer, /
    ) -> None:
        if type == genvmhost.ResultCode.RETURN:
            self._result = ExecutionReturn(ret=bytes(data))
        elif type == genvmhost.ResultCode.ROLLBACK:
            self._result = ExecutionRollback(str(data, encoding="utf-8"))

    async def get_leader_nondet_result(self, call_no: int, /) -> bytes | str | None:
        leader_results = self._leader_results
        if leader_results is None:
            return None
        if not call_no in leader_results:
            raise Exception(
                f"There is no output for nondeterministic block call #{call_no}, most likely leader's execution failed there. Handling this scenario is WIP, but it's likely that it is not desired. Please, inspect leaders execution result"
            )
        leader_results_mem = memoryview(leader_results[call_no])
        if leader_results_mem[0] == genvmhost.ResultCode.ROLLBACK:
            return str(leader_results_mem[1:], "utf-8")
        if leader_results_mem[0] == genvmhost.ResultCode.RETURN:
            return bytes(leader_results_mem[1:])
        assert False

    async def post_nondet_result(
        self, call_no: int, type: genvmhost.ResultCode, data: collections.abc.Buffer, /
    ) -> None:
        barr = bytearray()
        barr.append(type.value)
        barr.extend(memoryview(data))
        self._eq_outputs[call_no] = bytes(barr)

    async def post_message(
        self, gas: int, account: bytes, calldata: bytes, code: bytes, /
    ) -> None:
        self._pending_transactions.append(
            PendingTransaction(Address(account).as_hex, calldata)
        )

    async def consume_gas(self, gas: int, /) -> None:
        pass


async def _run_genvm_host(
    host_supplier: typing.Callable[[socket.socket], _Host],
    args: list[Path | str],
    config: str | None,
) -> ExecutionResult:
    tmpdir = Path(tempfile.mkdtemp())
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock_listener:
            sock_listener.setblocking(False)
            sock_path = tmpdir.joinpath("sock")
            sock_listener.bind(str(sock_path))
            sock_listener.listen(1)

            new_args = [
                get_genvm_path(),
                "run",
                "--host",
                f"unix://{sock_path}",
                "--print=shrink",
            ]

            if config is not None:
                conf_path = tmpdir.joinpath("conf.json")
                conf_path.write_text(config)
                new_args.extend(["--config", conf_path])
            new_args.extend(args)

            host: _Host = host_supplier(sock_listener)  # _Host(sock_listener)
            try:
                return host.provide_result(
                    await genvmhost.run_host_and_program(host, new_args), None
                )
            finally:
                if host.sock is not None:
                    host.sock.close()
    except Exception as e:
        return ExecutionResult(
            result=ExecutionFail([e]),
            eq_outputs={},
            pending_transactions=[],
            stdout="",
            stderr="",
            genvm_log="",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
