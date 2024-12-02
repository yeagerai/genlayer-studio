from collections import defaultdict
from typing import Callable
from unittest.mock import AsyncMock, Mock
import time
import threading
import asyncio
import pytest
from backend.consensus.base import ConsensusAlgorithm
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.models import TransactionStatus
from backend.domain.types import Transaction, TransactionType
from backend.node.base import Node
from backend.node.types import ExecutionMode, ExecutionResultStatus, Receipt, Vote
from backend.protocol_rpc.message_handler.base import MessageHandler

DEFAULT_FINALITY_WINDOW = 5
DEFAULT_EXEC_RESULT = b"\x00\x00"  # success(null)


class AccountsManagerMock:
    def __init__(self, accounts: dict[str, int] | None = None):
        self.accounts = accounts or defaultdict(int)

    def get_account_balance(self, address: str) -> int:
        return self.accounts[address]

    def update_account_balance(self, address: str, balance: int):
        self.accounts[address] = balance


class TransactionsProcessorMock:
    def __init__(self, transactions=None):
        self.transactions = transactions or []
        self.updated_transaction_status_history = defaultdict(list)

    def get_transaction_by_hash(self, transaction_hash: str) -> dict:
        for transaction in self.transactions:
            if transaction["hash"] == transaction_hash:
                return transaction
        raise ValueError(f"Transaction with hash {transaction_hash} not found")

    def update_transaction_status(
        self, transaction_hash: str, status: TransactionStatus
    ):
        self.get_transaction_by_hash(transaction_hash)["status"] = status
        self.updated_transaction_status_history[transaction_hash].append(status)

    def set_transaction_result(self, transaction_hash: str, consensus_data: dict):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["consensus_data"] = consensus_data

    def set_transaction_appeal(self, transaction_hash: str, appeal: bool):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appealed"] = appeal

    def set_transaction_timestamp_accepted(
        self, transaction_hash: str, timestamp_accepted: int = None
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)
        if timestamp_accepted:
            transaction["timestamp_accepted"] = timestamp_accepted
        else:
            transaction["timestamp_accepted"] = int(time.time())

    def add_transaction(self, new_transaction: dict):
        self.transactions.append(new_transaction)

    def get_accepted_transactions(self):
        result = []
        for transaction in self.transactions:
            if transaction["status"] == TransactionStatus.ACCEPTED:
                result.append(transaction)
        return result

    def create_rollup_transaction(self, transaction_hash: str):
        pass


class SnapshotMock:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_all_validators(self):
        return self.nodes


def transaction_to_dict(transaction: Transaction) -> dict:
    return {
        "hash": transaction.hash,
        "status": transaction.status.value,
        "from_address": transaction.from_address,
        "to_address": transaction.to_address,
        "input_data": transaction.input_data,
        "data": transaction.data,
        "consensus_data": transaction.consensus_data,
        "nonce": transaction.nonce,
        "value": transaction.value,
        "type": transaction.type.value,
        "gaslimit": transaction.gaslimit,
        "r": transaction.r,
        "s": transaction.s,
        "v": transaction.v,
        "leader_only": transaction.leader_only,
        "appealed": transaction.appealed,
        "timestamp_accepted": transaction.timestamp_accepted,
    }


def dict_to_transaction(input: dict) -> Transaction:
    return Transaction(
        hash=input["hash"],
        status=TransactionStatus(input["status"]),
        type=TransactionType(input["type"]),
        from_address=input.get("from_address"),
        to_address=input.get("to_address"),
        input_data=input.get("input_data"),
        data=input.get("data"),
        consensus_data=input.get("consensus_data"),
        nonce=input.get("nonce"),
        value=input.get("value"),
        gaslimit=input.get("gaslimit"),
        r=input.get("r"),
        s=input.get("s"),
        v=input.get("v"),
        leader_only=input.get("leader_only", False),
        appealed=input.get("appealed"),
        timestamp_accepted=input.get("timestamp_accepted"),
    )


def contract_snapshot_factory(address: str):
    class ContractSnapshotMock:
        def __init__(self):
            self.address = address

        def update_contract_state(self, state: dict[str, str]):
            pass

    return ContractSnapshotMock()


def init_dummy_transaction():
    return Transaction(
        hash="transaction_hash",
        from_address="from_address",
        to_address="to_address",
        status=TransactionStatus.PENDING,
        type=TransactionType.RUN_CONTRACT,
    )


def get_nodes_specs(number_of_nodes: int):
    return [
        {
            "address": f"address{i}",
            "stake": i + 1,
            "provider": f"provider{i}",
            "model": f"model{i}",
            "config": f"config{i}",
        }
        for i in range(number_of_nodes)
    ]


async def _appeal_window(
    stop_event: threading.Event,
    transactions_processor: TransactionsProcessorMock,
    consensus: ConsensusAlgorithm,
):
    while not stop_event.is_set():
        accepted_transactions = transactions_processor.get_accepted_transactions()
        for transaction in accepted_transactions:
            transaction = dict_to_transaction(transaction)
            if not transaction.appealed:
                if (
                    int(time.time()) - transaction.timestamp_accepted
                ) > DEFAULT_FINALITY_WINDOW:
                    consensus.finalize_transaction(
                        transaction,
                        transactions_processor,
                        contract_snapshot_factory=contract_snapshot_factory,
                    )
            else:
                transactions_processor.set_transaction_appeal(transaction.hash, False)
                consensus.commit_reveal_accept_transaction(
                    transaction, transactions_processor
                )

        await asyncio.sleep(1)


def run_async_task_in_thread(
    stop_event: threading.Event,
    transactions_processor: TransactionsProcessorMock,
    consensus: ConsensusAlgorithm,
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _appeal_window(stop_event, transactions_processor, consensus)
        )
    finally:
        loop.close()


@pytest.fixture
def managed_thread(request):
    def start_thread(
        transactions_processor: TransactionsProcessorMock, consensus: ConsensusAlgorithm
    ):
        stop_event = threading.Event()
        thread = threading.Thread(
            target=run_async_task_in_thread,
            args=(stop_event, transactions_processor, consensus),
        )
        thread.start()

        def fin():
            stop_event.set()
            thread.join()

        request.addfinalizer(fin)

        return thread

    return start_thread


def node_factory(
    node: dict,
    mode: ExecutionMode,
    contract_snapshot: ContractSnapshot,
    receipt: Receipt | None,
    msg_handler: MessageHandler,
    contract_snapshot_factory: Callable[[str], ContractSnapshot],
    vote: Vote,
):
    mock = Mock(Node)

    mock.validator_mode = mode
    mock.address = node["address"]
    mock.leader_receipt = receipt

    mock.exec_transaction = AsyncMock(
        return_value=Receipt(
            vote=vote,
            class_name="",
            calldata=b"",
            mode=mode,
            gas_used=0,
            contract_state={},
            returned=DEFAULT_EXEC_RESULT,
            node_config={},
            eq_outputs={},
            execution_result=ExecutionResultStatus.SUCCESS,
            error=None,
        )
    )

    return mock
