from collections import defaultdict
from typing import Callable
from unittest.mock import AsyncMock, Mock, MagicMock
import time
import threading
import pytest
from backend.consensus.base import (
    ConsensusAlgorithm,
)
from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.models import TransactionStatus
from backend.domain.types import Transaction, TransactionType
from backend.node.base import Node
from backend.node.types import ExecutionMode, ExecutionResultStatus, Receipt, Vote
from backend.protocol_rpc.message_handler.base import MessageHandler

DEFAULT_FINALITY_WINDOW = 5
DEFAULT_CONSENSUS_SLEEP_TIME = 2
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
        self.status_changed_event = threading.Event()

    def get_transaction_by_hash(self, transaction_hash: str) -> dict:
        for transaction in self.transactions:
            if transaction["hash"] == transaction_hash:
                return transaction
        raise ValueError(f"Transaction with hash {transaction_hash} not found")

    def update_transaction_status(
        self, transaction_hash: str, status: TransactionStatus
    ):
        self.get_transaction_by_hash(transaction_hash)["status"] = status.value
        self.updated_transaction_status_history[transaction_hash].append(status)
        self.status_changed_event.set()

    def set_transaction_result(self, transaction_hash: str, consensus_data: dict):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["consensus_data"] = consensus_data

    def set_transaction_appeal(self, transaction_hash: str, appeal: bool):
        transaction = self.get_transaction_by_hash(transaction_hash)
        if appeal:
            if (transaction["status"] == TransactionStatus.ACCEPTED.value) or (
                transaction["status"] == TransactionStatus.UNDETERMINED.value
            ):
                transaction["appealed"] = appeal
                self.set_transaction_timestamp_appeal(transaction, int(time.time()))
        else:
            transaction["appealed"] = appeal

    def set_transaction_timestamp_awaiting_finalization(
        self, transaction_hash: str, timestamp_awaiting_finalization: int = None
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)
        if timestamp_awaiting_finalization:
            transaction["timestamp_awaiting_finalization"] = (
                timestamp_awaiting_finalization
            )
        else:
            transaction["timestamp_awaiting_finalization"] = int(time.time())

    def get_accepted_undetermined_transactions(self):
        accepted_undetermined_transactions = []
        for transaction in self.transactions:
            if (transaction["status"] == TransactionStatus.ACCEPTED.value) or (
                transaction["status"] == TransactionStatus.UNDETERMINED.value
            ):
                accepted_undetermined_transactions.append(transaction)

        accepted_undetermined_transactions = sorted(
            accepted_undetermined_transactions, key=lambda x: x["created_at"]
        )

        # Group transactions by address
        transactions_by_address = defaultdict(list)
        for transaction in accepted_undetermined_transactions:
            address = transaction["to_address"]
            transactions_by_address[address].append(transaction)
        return transactions_by_address

    def create_rollup_transaction(self, transaction_hash: str):
        pass

    def set_transaction_appeal_failed(self, transaction_hash: str, appeal_failed: int):
        if appeal_failed < 0:
            raise ValueError("appeal_failed must be a non-negative integer")
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_failed"] = appeal_failed

    def set_transaction_appeal_undetermined(
        self, transaction_hash: str, appeal_undetermined: bool
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_undetermined"] = appeal_undetermined

    def get_pending_transactions(self):
        result = []
        for transaction in self.transactions:
            if transaction["status"] == TransactionStatus.PENDING.value:
                result.append(transaction)
        return sorted(result, key=lambda x: x["created_at"])

    def get_newer_transactions(self, transaction_hash: str):
        return []

    def set_transaction_timestamp_appeal(
        self, transaction: dict | str, timestamp_appeal: int
    ):
        if isinstance(transaction, str):  # hash
            transaction = self.get_transaction_by_hash(transaction)
        transaction["timestamp_appeal"] = timestamp_appeal

    def set_transaction_appeal_processing_time(self, transaction_hash: str):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_processing_time"] += (
            round(time.time()) - transaction["timestamp_appeal"]
        )

    def reset_transaction_appeal_processing_time(self, transaction_hash: str):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_processing_time"] = 0


class SnapshotMock:
    def __init__(self, nodes: list, transactions_processor: TransactionsProcessorMock):
        self.nodes = nodes
        self.transactions_processor = transactions_processor

    def get_all_validators(self):
        return self.nodes

    def get_pending_transactions(self):
        return self.transactions_processor.get_pending_transactions()

    def get_accepted_undetermined_transactions(self):
        return self.transactions_processor.get_accepted_undetermined_transactions()


class ContractSnapshotMock:
    def __init__(self, address: str):
        self.address = address

    def update_contract_state(self, state: dict[str, str]):
        pass


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
        "created_at": transaction.created_at,
        "ghost_contract_address": transaction.ghost_contract_address,
        "appealed": transaction.appealed,
        "timestamp_awaiting_finalization": transaction.timestamp_awaiting_finalization,
        "appeal_failed": transaction.appeal_failed,
        "appeal_undetermined": transaction.appeal_undetermined,
        "timestamp_appeal": transaction.timestamp_appeal,
        "appeal_processing_time": transaction.appeal_processing_time,
    }


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
            calldata=b"",
            mode=mode,
            gas_used=0,
            contract_state={},
            result=DEFAULT_EXEC_RESULT,
            node_config={"address": node["address"]},
            eq_outputs={},
            execution_result=ExecutionResultStatus.SUCCESS,
        )
    )

    return mock


def appeal(transaction: Transaction, transactions_processor: TransactionsProcessorMock):
    transactions_processor.status_changed_event.clear()
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == False
    )
    transactions_processor.set_transaction_appeal(transaction.hash, True)
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == True
    )


def check_validator_count(
    transaction: Transaction, transactions_processor: TransactionsProcessor, n: int
):
    assert (
        len(
            transactions_processor.get_transaction_by_hash(transaction.hash)[
                "consensus_data"
            ]["validators"]
        )
        == n - 1  # -1 because of the leader
    )


def get_leader_address(
    transaction: Transaction, transactions_processor: TransactionsProcessor
):
    transaction_dict = transactions_processor.get_transaction_by_hash(transaction.hash)
    return transaction_dict["consensus_data"]["leader_receipt"]["node_config"][
        "address"
    ]


def get_validator_addresses(
    transaction: Transaction, transactions_processor: TransactionsProcessor
):
    transaction_dict = transactions_processor.get_transaction_by_hash(transaction.hash)
    return {
        validator["node_config"]["address"]
        for validator in transaction_dict["consensus_data"]["validators"]
    }


@pytest.fixture
def consensus_algorithm() -> ConsensusAlgorithm:
    class MessageHandlerMock:
        def send_message(self, log_event, log_to_terminal: bool = True):
            print(log_event)

    # Mock the session and other dependencies
    mock_session = MagicMock()
    mock_msg_handler = MessageHandlerMock()

    consensus_algorithm = ConsensusAlgorithm(
        get_session=lambda: mock_session, msg_handler=mock_msg_handler
    )
    consensus_algorithm.finality_window_time = DEFAULT_FINALITY_WINDOW
    consensus_algorithm.consensus_sleep_time = DEFAULT_CONSENSUS_SLEEP_TIME
    return consensus_algorithm


def setup_test_environment(
    consensus_algorithm: ConsensusAlgorithm,
    transactions_processor: TransactionsProcessorMock,
    nodes: list,
    created_nodes: list,
    get_vote: Callable[[], Vote],
):
    chain_snapshot = SnapshotMock(nodes, transactions_processor)
    accounts_manager = AccountsManagerMock()

    chain_snapshot_factory = lambda session: chain_snapshot
    transactions_processor_factory = lambda session: transactions_processor
    accounts_manager_factory = lambda session: accounts_manager
    contract_snapshot_factory = (
        lambda address, session, transaction: ContractSnapshotMock(address)
    )
    node_factory_supplier = (
        lambda node, mode, contract_snapshot, receipt, msg_handler, contract_snapshot_factory: created_nodes.append(
            node_factory(
                node,
                mode,
                contract_snapshot,
                receipt,
                msg_handler,
                contract_snapshot_factory,
                get_vote(),
            )
        )
        or created_nodes[-1]
    )

    # Create a stop event
    stop_event = threading.Event()

    # Start the crawl_snapshot, process_pending_transactions and appeal_window threads
    thread_crawl_snapshot = threading.Thread(
        target=consensus_algorithm.run_crawl_snapshot_loop,
        args=(chain_snapshot_factory, transactions_processor_factory, stop_event),
    )
    thread_process_pending_transactions = threading.Thread(
        target=consensus_algorithm.run_process_pending_transactions_loop,
        args=(
            chain_snapshot_factory,
            transactions_processor_factory,
            accounts_manager_factory,
            contract_snapshot_factory,
            node_factory_supplier,
            stop_event,
        ),
    )
    thread_appeal_window = threading.Thread(
        target=consensus_algorithm.run_appeal_window_loop,
        args=(
            chain_snapshot_factory,
            transactions_processor_factory,
            accounts_manager_factory,
            contract_snapshot_factory,
            node_factory_supplier,
            stop_event,
        ),
    )

    thread_crawl_snapshot.start()
    thread_process_pending_transactions.start()
    thread_appeal_window.start()

    return (
        stop_event,
        thread_crawl_snapshot,
        thread_process_pending_transactions,
        thread_appeal_window,
    )


def cleanup_threads(event: threading.Event, threads: list[threading.Thread]):
    event.set()
    for thread in threads:
        thread.join()


def wait_for_condition(
    condition_func: Callable[[], bool], timeout: int = 5, interval: float = 0.1
):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False


def assert_transaction_status_match(
    transactions_processor: TransactionsProcessorMock,
    transaction: Transaction,
    expected_statuses: list[TransactionStatus],
    timeout: int = 30,
    interval: float = 0.1,
) -> TransactionStatus:
    status = None

    def condition():
        nonlocal status
        status = transactions_processor.get_transaction_by_hash(transaction.hash)[
            "status"
        ]
        return status in expected_statuses

    assert wait_for_condition(
        condition,
        timeout=timeout,
        interval=interval,
    ), f"Transaction did not reach {expected_statuses}"

    return status


def assert_transaction_status_change_and_match(
    transactions_processor: TransactionsProcessorMock,
    transaction: Transaction,
    expected_statuses: list[TransactionStatus],
    timeout: int = 30,
    interval: float = 0.1,
):
    transactions_processor.status_changed_event.wait()
    assert_transaction_status_match(
        transactions_processor,
        transaction,
        expected_statuses,
        timeout=timeout,
        interval=interval,
    )
