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
import datetime
import abc

from backend.node.types import (
    PendingTransaction,
    Address,
)
import backend.node.genvm.origin.calldata as calldata
from dataclasses import dataclass

from backend.node.genvm.config import get_genvm_path
from .origin.result_codes import *
from .origin.host_fns import Errors


@dataclass
class ExecutionError:
    message: str
    kind: typing.Literal[ResultCode.USER_ERROR, ResultCode.VM_ERROR]

    def __repr__(self):
        return json.dumps({"kind": self.kind.name, "message": self.message})


@dataclass
class ExecutionReturn:
    ret: bytes

    def __repr__(self):
        return json.dumps(
            {"kind": "return", "data": base64.b64encode(self.ret).decode("ascii")}
        )


@dataclass
class ExecutionResult:
    result: ExecutionReturn | ExecutionError
    eq_outputs: dict[int, bytes]
    pending_transactions: list[PendingTransaction]
    stdout: str
    stderr: str
    genvm_log: list


def encode_result_to_bytes(result: ExecutionReturn | ExecutionError) -> bytes:
    if isinstance(result, ExecutionReturn):
        return bytes([ResultCode.RETURN]) + result.ret
    if isinstance(result, ExecutionError):
        return bytes([result.kind]) + result.message.encode("utf-8")


# Interface for accessing the blockchain state, it is needed to not tangle current (awfully unoptimized)
# storage format with the genvm source code
class StateProxy(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def storage_read(
        self, account: Address, slot: bytes, index: int, le: int, /
    ) -> bytes: ...
    @abc.abstractmethod
    def storage_write(
        self,
        account: Address,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None: ...
    @abc.abstractmethod
    def get_balance(self, addr: Address) -> int: ...


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
        date: datetime.datetime | None,
        chain_id: int,
        host_data: typing.Any,
        readonly: bool,
        config_path: Path | None,
    ) -> ExecutionResult: ...

    async def get_contract_schema(self, contract_code: bytes) -> ExecutionResult: ...


# state proxy that always fails and can give code only for address from a constructor
# useful for get_schema
class _StateProxyNone(StateProxy):
    data: dict[bytes, bytearray]

    def __init__(self, my_address: Address):
        self.my_address = my_address
        self.data = {}

    def storage_read(
        self, account: Address, slot: bytes, index: int, le: int, /
    ) -> bytes:
        assert account == self.my_address
        res = self.data.setdefault(slot, bytearray())
        return res[index : index + le] + b"\x00" * (le - max(0, len(res) - index))

    def storage_write(
        self,
        account: Address,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None:
        assert account == self.my_address
        res = self.data.setdefault(slot, bytearray())
        what = memoryview(got)
        res.extend(b"\x00" * (index + len(what) - len(res)))
        memoryview(res)[index : index + len(what)] = what

    def get_balance(self, addr: Address) -> int:
        return 0


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
        readonly: bool,
        leader_results: None | dict[int, bytes],
        date: datetime.datetime | None,
        chain_id: int,
        host_data: typing.Any,
        config_path: Path | None,
    ) -> ExecutionResult:
        message = {
            "is_init": is_init,
            "contract_address": contract_address.as_b64,
            "sender_address": from_address.as_b64,
            "origin_address": from_address.as_b64,  # FIXME: no origin in simulator #751
            "value": None,
            "chain_id": str(
                chain_id
            ),  # NOTE: it can overflow u64 so better to wrap it into a string
        }
        if date is not None:
            assert date.tzinfo is not None
            message["datetime"] = date.isoformat()
        perms = "rcn"  # read/call/spawn nondet
        if not readonly:
            perms += "ws"  # write/send
        return await _run_genvm_host(
            functools.partial(
                _Host,
                calldata_bytes=calldata_raw,
                state_proxy=state,
                leader_results=leader_results,
            ),
            [
                "--message",
                json.dumps(message),
                "--permissions",
                perms,
                "--host-data",
                json.dumps(host_data),
                "--allow-latest",
            ],
            config_path,
        )

    async def get_contract_schema(self, contract_code: bytes) -> ExecutionResult:
        NO_ADDR = str(base64.b64encode(b"\x00" * 20), encoding="ascii")
        message = {
            "is_init": False,
            "contract_address": NO_ADDR,
            "sender_address": NO_ADDR,
            "origin_address": NO_ADDR,
            "value": None,
            "chain_id": "0",
        }
        state_proxy = _StateProxyNone(Address(NO_ADDR))
        genvmhost.save_code_callback(
            state_proxy.my_address.as_bytes,
            contract_code,
            lambda addr, *rest: state_proxy.storage_write(Address(addr), *rest),
        )
        # state_proxy.storage_write()
        return await _run_genvm_host(
            functools.partial(
                _Host,
                calldata_bytes=calldata.encode({"method": "#get-schema"}),
                state_proxy=state_proxy,
                leader_results=None,
            ),
            ["--message", json.dumps(message), "--permissions", "", "--allow-latest"],
            None,
        )


def _decode_genvm_log(log: str) -> list:
    decoded: list = []
    for log_line in log.splitlines():
        try:
            decoded.append(json.loads(log_line))
        except Exception:
            decoded.append(log_line)
    return decoded


# Class that has logic for handling all genvm host methods and accumulating results
class _Host(genvmhost.IHost):
    _result: ExecutionReturn | ExecutionError | None
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

    def provide_result(self, res: genvmhost.RunHostAndProgramRes) -> ExecutionResult:
        assert self._result is not None
        return ExecutionResult(
            eq_outputs=self._eq_outputs,
            pending_transactions=self._pending_transactions,
            stdout=res.stdout,
            stderr=res.stderr,
            genvm_log=_decode_genvm_log(res.genvm_log),
            result=self._result,
        )

    async def loop_enter(self) -> socket.socket:
        async_loop = asyncio.get_event_loop()
        self.sock, _addr = await async_loop.sock_accept(self.sock_listen)
        self.sock.setblocking(False)
        self.sock_listen.close()
        return self.sock

    async def get_calldata(self, /) -> bytes:
        return self.calldata_bytes

    def has_result(self) -> bool:
        return self._result is not None

    async def storage_read(
        self, type: StorageType, account: bytes, slot: bytes, index: int, le: int, /
    ) -> bytes:
        assert type != StorageType.LATEST_FINAL
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
        self, type: ResultCode, data: collections.abc.Buffer, /
    ) -> None:
        if type == ResultCode.RETURN:
            self._result = ExecutionReturn(ret=bytes(data))
        elif type == ResultCode.USER_ERROR:
            self._result = ExecutionError(str(data, encoding="utf-8"), type)
        elif type == ResultCode.VM_ERROR:
            self._result = ExecutionError(str(data, encoding="utf-8"), type)
        elif type == ResultCode.INTERNAL_ERROR:
            raise Exception("GenVM internal error", str(data, encoding="utf-8"))
        else:
            assert False, f"invalid result {type}"

    async def get_leader_nondet_result(
        self, call_no: int, /
    ) -> tuple[ResultCode, collections.abc.Buffer] | Errors:
        leader_results = self._leader_results
        if leader_results is None:
            return Errors.I_AM_LEADER
        res = leader_results.get(call_no, None)
        if res is None:
            return Errors.ABSENT
        leader_results_mem = memoryview(res)
        return (ResultCode(leader_results_mem[0]), leader_results_mem[1:])

    async def post_nondet_result(
        self, call_no: int, type: genvmhost.ResultCode, data: collections.abc.Buffer, /
    ) -> None:
        encoded_result = bytearray()
        encoded_result.append(type.value)
        encoded_result.extend(memoryview(data))
        self._eq_outputs[call_no] = bytes(encoded_result)

    async def post_message(
        self, account: bytes, calldata: bytes, data: genvmhost.DefaultTransactionData, /
    ) -> None:
        on = data.get("on", "finalized")
        value = int(data.get("value", "0x0"), 16)
        self._pending_transactions.append(
            PendingTransaction(
                Address(account).as_hex,
                calldata,
                code=None,
                salt_nonce=0,
                value=value,
                on=on,
            )
        )

    async def consume_gas(self, gas: int, /) -> None:
        pass

    async def deploy_contract(
        self,
        calldata: bytes,
        code: bytes,
        data: genvmhost.DeployDefaultTransactionData,
        /,
    ) -> None:
        on = data.get("on", "finalized")
        value = int(data.get("value", "0x0"), 16)
        salt_nonce = int(data.get("salt_nonce", "0x0"), 16)
        self._pending_transactions.append(
            PendingTransaction(
                address="0x",
                calldata=calldata,
                code=code,
                salt_nonce=salt_nonce,
                value=value,
                on=on,
            )
        )

    async def eth_send(
        self,
        account: bytes,
        calldata: bytes,
        data: genvmhost.DefaultEthTransactionData,
        /,
    ) -> None:
        # FIXME(core-team): #748
        assert False

    async def eth_call(self, account: bytes, calldata: bytes, /) -> bytes:
        # FIXME(core-team): #748
        assert False

    async def get_balance(self, account: bytes, /) -> int:
        return self._state_proxy.get_balance(Address(account))


async def _run_genvm_host(
    host_supplier: typing.Callable[[socket.socket], _Host],
    args: list[Path | str],
    config_path: Path | None,
) -> ExecutionResult:
    tmpdir = Path(tempfile.mkdtemp())
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock_listener:
            timeout = 300  # seconds

            sock_listener.setblocking(False)
            sock_path = tmpdir.joinpath("sock")
            sock_listener.bind(str(sock_path))
            sock_listener.listen(1)

            new_args: list[str | Path] = [
                get_genvm_path(),
            ]
            if config_path is not None:
                new_args.extend(["--config", config_path])
            new_args.extend(
                [
                    "run",
                    "--host",
                    f"unix://{sock_path}",
                    "--print=none",
                ]
            )

            new_args.extend(args)

            host: _Host = host_supplier(sock_listener)  # _Host(sock_listener)
            try:
                return host.provide_result(
                    await genvmhost.run_host_and_program(
                        host, new_args, deadline=timeout
                    )
                )
            finally:
                if host.sock is not None:
                    host.sock.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
