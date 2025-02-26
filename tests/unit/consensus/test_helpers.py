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
from typing import Optional

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
        self.status_update_lock = threading.Lock()

    def get_transaction_by_hash(self, transaction_hash: str) -> dict:
        for transaction in self.transactions:
            if transaction["hash"] == transaction_hash:
                return transaction
        raise ValueError(f"Transaction with hash {transaction_hash} not found")

    def update_transaction_status(
        self, transaction_hash: str, new_status: TransactionStatus
    ):
        with self.status_update_lock:
            transaction = self.get_transaction_by_hash(transaction_hash)
            transaction["status"] = new_status.value
            self.updated_transaction_status_history[transaction_hash].append(new_status)

            if "current_status_changes" in transaction["consensus_history"]:
                transaction["consensus_history"]["current_status_changes"].append(
                    new_status.value
                )
            else:
                transaction["consensus_history"]["current_status_changes"] = [
                    TransactionStatus.PENDING.value,
                    new_status.value,
                ]

            self.status_changed_event.set()

    def wait_for_status_change(self, timeout: float = 0.1) -> bool:
        result = self.status_changed_event.wait(timeout)
        self.status_changed_event.clear()
        return result

    def set_transaction_result(self, transaction_hash: str, consensus_data: dict):
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["consensus_data"] = consensus_data

    def set_transaction_appeal(self, transaction_hash: str, appeal: bool):
        transaction = self.get_transaction_by_hash(transaction_hash)
        if not appeal:
            transaction["appealed"] = appeal
        elif transaction["status"] in (
            TransactionStatus.ACCEPTED.value,
            TransactionStatus.UNDETERMINED.value,
        ):
            if transaction["appeal_round"] < transaction["config_appeal_rounds"]:
                transaction["appealed"] = appeal
                self.set_transaction_timestamp_appeal(transaction, int(time.time()))
            else:
                raise ValueError(
                    "Transaction has already been appealed the maximum number of times"
                )

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

    def update_consensus_history(
        self,
        transaction_hash: str,
        consensus_round: str,
        leader_result: dict | None,
        validator_results: list,
    ):
        transaction = self.get_transaction_by_hash(transaction_hash)

        current_consensus_results = {
            "consensus_round": consensus_round,
            "leader_result": leader_result.to_dict() if leader_result else None,
            "validator_results": [receipt.to_dict() for receipt in validator_results],
            "status_changes": (
                transaction["consensus_history"]["current_status_changes"]
                if "current_status_changes" in transaction["consensus_history"]
                else []
            ),
        }
        if "consensus_results" in transaction["consensus_history"]:
            transaction["consensus_history"]["consensus_results"].append(
                current_consensus_results
            )
        else:
            transaction["consensus_history"]["consensus_results"] = [
                current_consensus_results
            ]

        transaction["consensus_history"]["current_status_changes"] = []

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

    def set_transaction_contract_snapshot(
        self, transaction_hash: str, contract_snapshot: dict
    ):
        pass

    def get_transaction_contract_snapshot(self, transaction_hash: str):
        return None

    def set_transaction_appeal_round(self, transaction_hash: str, appeal_round: int):
        if appeal_round < 0:
            raise ValueError("appeal_round must be a non-negative integer")
        transaction = self.get_transaction_by_hash(transaction_hash)
        transaction["appeal_round"] = appeal_round


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

    def register_contract(self, contract: dict):
        pass

    def update_contract_state(
        self,
        accepted_state: dict[str, str] | None = None,
        finalized_state: dict[str, str] | None = None,
    ):
        pass

    def to_dict(self):
        return {
            "address": (self.address if self.address else None),
        }

    @classmethod
    def from_dict(cls, input: dict | None) -> Optional["ContractSnapshotMock"]:
        if input:
            instance = cls.__new__(cls)
            instance.address = input.get("address", None)
            return instance
        else:
            return None


def transaction_to_dict(transaction: Transaction) -> dict:
    return {
        "hash": transaction.hash,
        "status": transaction.status.value,
        "from_address": transaction.from_address,
        "to_address": transaction.to_address,
        "input_data": transaction.input_data,
        "data": transaction.data,
        "consensus_data": (
            transaction.consensus_data.to_dict() if transaction.consensus_data else None
        ),
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
        "consensus_history": transaction.consensus_history,
        "timestamp_appeal": transaction.timestamp_appeal,
        "appeal_processing_time": transaction.appeal_processing_time,
        "contract_snapshot": (
            transaction.contract_snapshot.to_dict()
            if transaction.contract_snapshot
            else None
        ),
        "config_rotation_rounds": transaction.config_rotation_rounds,
        "config_appeal_rounds": transaction.config_appeal_rounds,
        "appeal_round": transaction.appeal_round,
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


def assert_transaction_status_match(
    transactions_processor: TransactionsProcessorMock,
    transaction: Transaction,
    expected_statuses: list[TransactionStatus],
    timeout: int = 30,
    interval: float = 0.1,
) -> TransactionStatus:
    last_status = None
    start_time = time.time()

    while time.time() - start_time < timeout:
        current_status = transactions_processor.get_transaction_by_hash(
            transaction.hash
        )["status"]

        if current_status in expected_statuses:
            return current_status

        if current_status != last_status:
            last_status = current_status

        # Wait for next status change
        transactions_processor.wait_for_status_change(interval)

    raise AssertionError(
        f"Transaction did not reach {expected_statuses} within {timeout} seconds. Last status: {last_status}"
    )


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
