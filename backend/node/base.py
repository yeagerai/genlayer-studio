from contextlib import redirect_stdout
from dataclasses import asdict
import datetime
import json
import base64
from typing import Callable, Optional
import typing
import collections.abc
import os

from backend.domain.types import Validator, Transaction, TransactionType
from backend.protocol_rpc.message_handler.types import LogEvent, EventType, EventScope
import backend.node.genvm.base as genvmbase
import backend.node.genvm.origin.calldata as calldata
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.node.types import Receipt, ExecutionMode, Vote, ExecutionResultStatus
from backend.protocol_rpc.message_handler.base import MessageHandler

from .types import Address

SIMULATOR_CHAIN_ID: typing.Final[int] = 61999


class _SnapshotView(genvmbase.StateProxy):
    def __init__(
        self,
        snapshot: ContractSnapshot,
        snapshot_factory: typing.Callable[[str], ContractSnapshot],
        readonly: bool,
    ):
        self.contract_address = Address(snapshot.contract_address)
        self.snapshot = snapshot
        self.snapshot_factory = snapshot_factory
        self.cached = {}
        self.readonly = readonly

    def _get_snapshot(self, addr: Address) -> ContractSnapshot:
        if addr == self.contract_address:
            return self.snapshot
        res = self.cached.get(addr)
        if res is not None:
            return res
        res = self.snapshot_factory(addr.as_hex)
        self.cached[addr] = res
        return res

    def get_code(self, addr: Address) -> bytes:
        return base64.b64decode(self._get_snapshot(addr).contract_code)

    def storage_read(
        self, account: Address, slot: bytes, index: int, le: int, /
    ) -> bytes:
        snap = self._get_snapshot(account)
        slot_id = base64.b64encode(slot).decode("ascii")
        for_slot = snap.encoded_state.setdefault(slot_id, "")
        data = bytearray(base64.b64decode(for_slot))
        data.extend(b"\x00" * (index + le - len(data)))
        return data[index : index + le]

    def storage_write(
        self,
        account: Address,
        slot: bytes,
        index: int,
        got: collections.abc.Buffer,
        /,
    ) -> None:
        assert account == self.contract_address
        assert not self.readonly
        snap = self._get_snapshot(account)
        slot_id = base64.b64encode(slot).decode("ascii")
        for_slot = snap.encoded_state.setdefault(slot_id, "")
        data = bytearray(base64.b64decode(for_slot))
        mem = memoryview(got)
        data.extend(b"\x00" * (index + len(mem) - len(data)))
        data[index : index + len(mem)] = mem
        snap.encoded_state[slot_id] = base64.b64encode(data).decode("utf-8")

    def get_balance(self, addr: Address) -> int:
        snap = self._get_snapshot(addr)
        # FIXME(core-team): it is not obvious where `value` is added to `self.balance`
        # but return must be increased by it
        return snap.balance


class Node:
    def __init__(
        self,
        contract_snapshot: ContractSnapshot | None,
        validator_mode: ExecutionMode,
        validator: Validator,
        contract_snapshot_factory: Callable[[str], ContractSnapshot] | None,
        leader_receipt: Optional[Receipt] = None,
        msg_handler: MessageHandler | None = None,
    ):
        self.contract_snapshot = contract_snapshot
        self.validator_mode = validator_mode
        self.validator = validator
        self.address = validator.address
        self.leader_receipt = leader_receipt
        self.msg_handler = msg_handler
        self.contract_snapshot_factory = contract_snapshot_factory

    def _create_genvm(self) -> genvmbase.IGenVM:
        return genvmbase.GenVMHost()

    async def exec_transaction(self, transaction: Transaction) -> Receipt:
        assert transaction.data is not None
        transaction_data = transaction.data
        assert transaction.from_address is not None
        if transaction.type == TransactionType.DEPLOY_CONTRACT:
            code = base64.b64decode(transaction_data["contract_code"])
            calldata = base64.b64decode(transaction_data["calldata"])
            receipt = await self.deploy_contract(
                transaction.from_address,
                code,
                calldata,
                transaction.hash,
                transaction.created_at,
            )
        elif transaction.type == TransactionType.RUN_CONTRACT:
            calldata = base64.b64decode(transaction_data["calldata"])
            receipt = await self.run_contract(
                transaction.from_address,
                calldata,
                transaction.hash,
                transaction.value,
                transaction.created_at,
            )
        else:
            raise Exception(f"unknown transaction type {transaction.type}")
        return receipt

    def _set_vote(self, receipt: Receipt) -> Receipt:
        leader_receipt = self.leader_receipt
        if self.validator_mode == ExecutionMode.LEADER:
            receipt.vote = Vote.AGREE
        elif (
            leader_receipt.execution_result == receipt.execution_result
            and leader_receipt.result == receipt.result
            and leader_receipt.contract_state == receipt.contract_state
            and leader_receipt.pending_transactions == receipt.pending_transactions
        ):
            receipt.vote = Vote.AGREE
        else:
            receipt.vote = Vote.DISAGREE

        return receipt

    def _date_from_str(self, date: str | None) -> datetime.datetime | None:
        if date is None:
            return None
        res = datetime.datetime.fromisoformat(date)
        if res.tzinfo is None:
            res = res.replace(tzinfo=datetime.UTC)
        return res

    async def deploy_contract(
        self,
        from_address: str,
        code_to_deploy: bytes,
        calldata: bytes,
        transaction_hash: str,
        transaction_created_at: str | None = None,
    ) -> Receipt:
        assert self.contract_snapshot is not None
        self.contract_snapshot.contract_code = base64.b64encode(code_to_deploy).decode(
            "ascii"
        )
        return await self._run_genvm(
            from_address,
            calldata,
            readonly=False,
            is_init=True,
            transaction_hash=transaction_hash,
            transaction_datetime=self._date_from_str(transaction_created_at),
        )

    async def run_contract(
        self,
        from_address: str,
        calldata: bytes,
        transaction_hash: str,
        transaction_value: int,
        transaction_created_at: str | None = None,
    ) -> Receipt:
        return await self._run_genvm(
            from_address,
            calldata,
            readonly=False,
            is_init=False,
            transaction_hash=transaction_hash,
            transaction_datetime=self._date_from_str(transaction_created_at),
            transaction_value=transaction_value,
        )

    async def get_contract_data(
        self,
        from_address: str,
        calldata: bytes,
    ) -> Receipt:
        return await self._run_genvm(
            from_address,
            calldata,
            readonly=True,
            is_init=False,
            transaction_datetime=datetime.datetime.now().astimezone(datetime.UTC),
        )

    async def _execution_finished(
        self, res: genvmbase.ExecutionResult, transaction_hash_str: str | None
    ):
        msg_handler = self.msg_handler
        if msg_handler is None:
            return
        msg_handler.send_message(
            LogEvent(
                name="execution_finished",
                type=(
                    EventType.INFO
                    if isinstance(res.result, genvmbase.ExecutionReturn)
                    else EventType.ERROR
                ),
                scope=EventScope.GENVM,
                message="execution finished",
                data={
                    "result": f"{res.result!r}",
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "genvm_log": res.genvm_log,
                },
                transaction_hash=transaction_hash_str,
            )
        )

    async def get_contract_schema(self, code: bytes) -> str:
        genvm = self._create_genvm()
        res = await genvm.get_contract_schema(code)
        await self._execution_finished(res, None)
        err_data = {
            "stdout": res.stdout,
            "stderr": res.stderr,
            "genvm_log": res.genvm_log,
            "result": f"{res.result!r}",
        }
        if not isinstance(res.result, genvmbase.ExecutionReturn):
            raise Exception("execution failed", err_data)
        ret_calldata = res.result.ret
        try:
            schema = calldata.decode(ret_calldata)
        except Exception as e:
            raise Exception(f"abi violation, can't parse calldata #{e}", err_data)
        if not isinstance(schema, str):
            raise Exception(
                f"abi violation, invalid return type #{type(schema)}", err_data
            )
        return schema

    async def _run_genvm(
        self,
        from_address: str,
        calldata: bytes,
        *,
        readonly: bool,
        is_init: bool,
        transaction_hash: str | None = None,
        transaction_datetime: datetime.datetime | None,
        transaction_value: int | None = None,
    ) -> Receipt:
        genvm = self._create_genvm()
        leader_res: None | dict[int, bytes]
        if self.leader_receipt is None:
            leader_res = None
        else:
            leader_res = {
                k: base64.b64decode(v)
                for k, v in self.leader_receipt.eq_outputs.items()
            }
        assert self.contract_snapshot is not None
        assert self.contract_snapshot_factory is not None
        config = {
            "modules": [
                {
                    "path": "${genvmRoot}/lib/genvm-modules/",
                    "id": "llm",
                    "config": {
                        "host": f"{os.environ['WEBREQUESTPROTOCOL']}://{os.environ['WEBREQUESTHOST']}:{os.environ['WEBREQUESTPORT']}",
                        "provider": "simulator",
                        "model": json.dumps(self.validator.llmprovider.__dict__),
                    },
                },
                {
                    "path": "${genvmRoot}/lib/genvm-modules/",
                    "id": "web",
                    "config": {
                        "host": f"{os.environ['WEBREQUESTPROTOCOL']}://{os.environ['WEBREQUESTHOST']}:{os.environ['WEBREQUESTSELENIUMPORT']}"
                    },
                },
            ]
        }
        snapshot_view = _SnapshotView(
            self.contract_snapshot, self.contract_snapshot_factory, readonly
        )

        result_exec_code: ExecutionResultStatus
        res = await genvm.run_contract(
            snapshot_view,
            contract_address=Address(self.contract_snapshot.contract_address),
            from_address=Address(from_address),
            calldata_raw=calldata,
            is_init=is_init,
            readonly=readonly,
            leader_results=leader_res,
            config=json.dumps(config),
            date=transaction_datetime,
            chain_id=SIMULATOR_CHAIN_ID,
            value=transaction_value,
        )
        await self._execution_finished(res, transaction_hash)

        result_exec_code = (
            ExecutionResultStatus.SUCCESS
            if isinstance(res.result, genvmbase.ExecutionReturn)
            else ExecutionResultStatus.ERROR
        )

        return self._set_vote(
            Receipt(
                result=genvmbase.encode_result_to_bytes(res.result),
                gas_used=0,
                eq_outputs={
                    k: base64.b64encode(v).decode("ascii")
                    for k, v in res.eq_outputs.items()
                },
                pending_transactions=res.pending_transactions,
                vote=None,
                execution_result=result_exec_code,
                contract_state=self.contract_snapshot.encoded_state,
                calldata=calldata,
                mode=self.validator_mode,
                node_config=self.validator.to_dict(),
                genvm_result={
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                },
            )
        )
