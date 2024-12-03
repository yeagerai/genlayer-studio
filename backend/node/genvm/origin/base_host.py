import socket
import typing
import collections.abc
import asyncio
import os

from dataclasses import dataclass

from pathlib import Path

if typing.TYPE_CHECKING:
    from .host_fns import *
    from .result_codes import *
else:
    from pathlib import Path

    exec(Path(__file__).parent.joinpath("host_fns.py").read_text())
    exec(Path(__file__).parent.joinpath("result_codes.py").read_text())

ACCOUNT_ADDR_SIZE = 20
GENERIC_ADDR_SIZE = 32


class IHost(typing.Protocol):
    async def loop_enter(self) -> socket.socket: ...

    async def get_calldata(self, /) -> bytes: ...
    async def get_code(self, addr: bytes, /) -> bytes: ...
    async def storage_read(
        self, account: bytes, slot: bytes, index: int, le: int, /
    ) -> bytes: ...
    async def storage_write(
        self,
        account: bytes,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None: ...
    async def consume_result(
        self, type: ResultCode, data: collections.abc.Buffer, /
    ) -> None: ...
    async def get_leader_nondet_result(
        self, call_no: int, /
    ) -> tuple[ResultCode, collections.abc.Buffer] | None: ...
    async def post_nondet_result(
        self, call_no: int, type: ResultCode, data: collections.abc.Buffer, /
    ) -> None: ...
    async def post_message(
        self, gas: int, account: bytes, calldata: bytes, code: bytes, /
    ) -> None: ...
    async def consume_gas(self, gas: int, /) -> None: ...


async def host_loop(handler: IHost):
    async_loop = asyncio.get_event_loop()

    sock = await handler.loop_enter()

    async def send_all(data: collections.abc.Buffer):
        await async_loop.sock_sendall(sock, data)

    async def read_exact(le: int) -> bytes:
        buf = bytearray([0] * le)
        idx = 0
        while idx < le:
            read = await async_loop.sock_recv_into(sock, memoryview(buf)[idx:le])
            if read == 0:
                raise ConnectionResetError()
            idx += read
        return bytes(buf)

    async def recv_int(bytes: int = 4) -> int:
        return int.from_bytes(await read_exact(bytes), byteorder="little", signed=False)

    async def send_int(i: int, bytes=4):
        await send_all(int.to_bytes(i, bytes, byteorder="little", signed=False))

    async def read_result() -> tuple[ResultCode, bytes]:
        type = await recv_int(1)
        le = await recv_int()
        data = await read_exact(le)
        return (ResultCode(type), data)

    while True:
        meth_id = Methods(await recv_int(1))
        match meth_id:
            case Methods.APPEND_CALLDATA:
                cd = await handler.get_calldata()
                await send_int(len(cd))
                await send_all(cd)
            case Methods.GET_CODE:
                addr = await read_exact(ACCOUNT_ADDR_SIZE)
                code = await handler.get_code(addr)
                await send_int(len(code))
                await send_all(code)
            case Methods.STORAGE_READ:
                account = await read_exact(ACCOUNT_ADDR_SIZE)
                slot = await read_exact(GENERIC_ADDR_SIZE)
                index = await recv_int()
                le = await recv_int()
                res = await handler.storage_read(account, slot, index, le)
                assert len(res) == le
                await send_all(res)
            case Methods.STORAGE_WRITE:
                account = await read_exact(ACCOUNT_ADDR_SIZE)
                slot = await read_exact(GENERIC_ADDR_SIZE)
                index = await recv_int()
                le = await recv_int()
                got = await read_exact(le)
                await handler.storage_write(account, slot, index, got)
            case Methods.CONSUME_RESULT:
                await handler.consume_result(*await read_result())
                await send_all(b"\x00")
                return
            case Methods.GET_LEADER_NONDET_RESULT:
                call_no = await recv_int()
                data = await handler.get_leader_nondet_result(call_no)
                if data is None:
                    await send_all(bytes([ResultCode.NONE]))
                    continue
                code, as_bytes = data
                as_bytes = memoryview(as_bytes)
                await send_all(bytes([code]))
                await send_int(len(as_bytes))
                await send_all(as_bytes)
            case Methods.POST_NONDET_RESULT:
                call_no = await recv_int()
                await handler.post_nondet_result(call_no, *await read_result())
            case Methods.POST_MESSAGE:
                account = await read_exact(ACCOUNT_ADDR_SIZE)
                gas = await recv_int(8)
                calldata_len = await recv_int()
                calldata = await read_exact(calldata_len)
                code_len = await recv_int()
                code = await read_exact(code_len)
                await handler.post_message(gas, account, calldata, code)
            case Methods.CONSUME_FUEL:
                gas = await recv_int(8)
                await handler.consume_gas(gas)
            case x:
                raise Exception(f"unknown method {x}")


@dataclass
class RunHostAndProgramRes:
    stdout: str
    stderr: str
    genvm_log: str


async def run_host_and_program(
    handler: IHost,
    program: list[Path | str],
    *,
    env=None,
    cwd: Path | None = None,
    exit_timeout=0.05,
    deadline: float | None = None,
) -> RunHostAndProgramRes:
    loop = asyncio.get_running_loop()

    async def connect_reader(fd):
        reader = asyncio.StreamReader(loop=loop)
        reader_proto = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.connect_read_pipe(
            lambda: reader_proto, os.fdopen(fd, "rb")
        )
        return reader, transport

    stdout_rfd, stdout_wfd = os.pipe()
    stderr_rfd, stderr_wfd = os.pipe()
    genvm_log_rfd, genvm_log_wfd = os.pipe()
    stdout_reader, stdout_transport = await connect_reader(stdout_rfd)
    stderr_reader, stderr_transport = await connect_reader(stderr_rfd)
    genvm_log_reader, genvm_log_transport = await connect_reader(genvm_log_rfd)

    process = await asyncio.create_subprocess_exec(
        program[0],
        "--log-fd",
        str(genvm_log_wfd),
        *program[1:],
        stdin=asyncio.subprocess.DEVNULL,
        stdout=stdout_wfd,
        stderr=stderr_wfd,
        cwd=cwd,
        env=env,
        pass_fds=(genvm_log_wfd,),
    )
    os.close(stdout_wfd)
    os.close(stderr_wfd)
    os.close(genvm_log_wfd)
    if process.stdin is not None:
        process.stdin.close()

    async def read_whole(reader, transport, put_to: list[bytes]):
        try:
            while True:
                read = await reader.read(4096)
                if read is None or len(read) == 0:
                    break
                put_to.append(read)
        finally:
            try:
                transport.close()
            except OSError:
                pass
            await asyncio.sleep(0)

    stdout, stderr, genvm_log = [], [], []

    async def wrap_proc():
        await asyncio.gather(
            read_whole(stdout_reader, stdout_transport, stdout),
            read_whole(stderr_reader, stderr_transport, stderr),
            read_whole(genvm_log_reader, genvm_log_transport, genvm_log),
            process.wait(),
        )

    coro_proc = asyncio.ensure_future(wrap_proc())

    async def wrap_host():
        await host_loop(handler)

    coro_loop = asyncio.ensure_future(wrap_host())

    all_proc = [coro_loop, coro_proc]
    if deadline is not None:
        all_proc.append(asyncio.ensure_future(asyncio.sleep(deadline)))

    done, _pending = await asyncio.wait(
        all_proc,
        return_when=asyncio.FIRST_COMPLETED,
    )

    errors = []

    for x in done:
        try:
            x.result()
        except Exception as e:
            errors.append(e)

    # coro_loop must finish first if everything succeeded
    if not coro_loop.done() and deadline is None:
        print("WARNING: genvm finished first")
        coro_loop.cancel()

    if not coro_proc.done():
        # genvm is exiting, let it clean all the resources for a bit
        await asyncio.wait(
            [coro_proc, asyncio.ensure_future(asyncio.sleep(exit_timeout))],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not coro_proc.done():
            # genvm exit takes to long, maybe it hanged. Politely ask to quit and wait a bit
            try:
                process.terminate()
            except:
                pass
            await asyncio.wait(
                [coro_proc, asyncio.ensure_future(asyncio.sleep(exit_timeout))],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not coro_proc.done():
                # genvm exit takes to long, forcefully quit it
                try:
                    process.kill()
                except:
                    pass

    await coro_proc
    exit_code = await process.wait()

    if not coro_loop.done():
        coro_loop.cancel()

    if len(errors) > 0:
        raise Exception(
            *errors,
            {
                "stdout": b"".join(stdout).decode(),
                "stderr": b"".join(stderr).decode(),
                "genvm_log": b"".join(genvm_log).decode(),
            },
        ) from errors[0]

    return RunHostAndProgramRes(
        b"".join(stdout).decode(),
        b"".join(stderr).decode(),
        b"".join(genvm_log).decode(),
    )
