from collections import defaultdict
from typing import Callable
from unittest.mock import AsyncMock, Mock

import pytest

from backend.consensus.base import ConsensusAlgorithm, rotate
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.models import TransactionStatus
from backend.domain.types import Transaction, TransactionType
from backend.node.base import Node
from backend.node.types import ExecutionMode, ExecutionResultStatus, Receipt, Vote
from backend.protocol_rpc.message_handler.base import MessageHandler

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
    }


def contract_snapshot_factory(address: str):
    class ContractSnapshotMock:
        def __init__(self):
            self.address = address

        def update_contract_state(self, state: dict[str, str]):
            pass

    return ContractSnapshotMock()


@pytest.mark.asyncio
async def test_exec_transaction():
    """
    Minor smoke checks for the happy path of a transaction execution
    """

    transaction = Transaction(
        hash="transaction_hash",
        from_address="from_address",
        to_address="to_address",
        status=TransactionStatus.PENDING,
        type=TransactionType.RUN_CONTRACT,
    )

    nodes = [
        {
            "address": "address1",
            "stake": 1,
            "provider": "provider1",
            "model": "model1",
            "config": "config1",
        },
        {
            "address": "address2",
            "stake": 2,
            "provider": "provider2",
            "model": "model2",
            "config": "config2",
        },
        {
            "address": "address3",
            "stake": 3,
            "provider": "provider3",
            "model": "model3",
            "config": "config3",
        },
    ]

    created_nodes = []

    def node_factory(
        node: dict,
        mode: ExecutionMode,
        contract_snapshot: ContractSnapshot,
        receipt: Receipt | None,
        msg_handler: MessageHandler,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
    ):
        mock = Mock(Node)

        mock.validator_mode = mode
        mock.address = node["address"]
        mock.leader_receipt = receipt

        mock.exec_transaction = AsyncMock(
            return_value=Receipt(
                result=DEFAULT_EXEC_RESULT,
                vote=Vote.AGREE,
                calldata=b"",
                mode=mode,
                gas_used=0,
                contract_state={},
                node_config={},
                eq_outputs={},
                execution_result=ExecutionResultStatus.SUCCESS,
            )
        )

        created_nodes.append(mock)

        return mock

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory,
    )

    assert len(created_nodes) == len(nodes)

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED
    )

    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": [
            TransactionStatus.PROPOSING,
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.ACCEPTED,
            TransactionStatus.FINALIZED,
        ]
    }


@pytest.mark.asyncio
async def test_exec_transaction_no_consensus():
    """
    Scenario: all nodes disagree on the transaction execution, leaving the transaction in UNDETERMINED state
    Tests that consensus algorithm correctly rotates the leader when majority of nodes disagree
    """

    transaction = Transaction(
        hash="transaction_hash",
        from_address="from_address",
        to_address="to_address",
        status=TransactionStatus.PENDING,
        type=TransactionType.RUN_CONTRACT,
    )

    nodes = [
        {
            "address": "address1",
            "stake": 1,
            "provider": "provider1",
            "model": "model1",
            "config": "config1",
        },
        {
            "address": "address2",
            "stake": 2,
            "provider": "provider2",
            "model": "model2",
            "config": "config2",
        },
        {
            "address": "address3",
            "stake": 3,
            "provider": "provider3",
            "model": "model3",
            "config": "config3",
        },
    ]

    created_nodes = []

    def node_factory(
        node: dict,
        mode: ExecutionMode,
        contract_snapshot: ContractSnapshot,
        receipt: Receipt | None,
        msg_handler: MessageHandler,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
    ):
        mock = Mock(Node)

        mock.validator_mode = mode
        mock.address = node["address"]
        mock.leader_receipt = receipt

        mock.exec_transaction = AsyncMock(
            return_value=Receipt(
                vote=Vote.DISAGREE,
                calldata=b"",
                mode=mode,
                gas_used=0,
                contract_state={},
                result=DEFAULT_EXEC_RESULT,
                node_config={},
                eq_outputs={},
                execution_result=ExecutionResultStatus.SUCCESS,
            )
        )

        created_nodes.append(mock)

        return mock

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory,
    )

    assert len(created_nodes) == len(nodes) ** 2

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": [
            TransactionStatus.PROPOSING,  # leader 1
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.PROPOSING,  # rotation, leader 2
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.PROPOSING,  # rotation, leader 3
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.UNDETERMINED,  # all disagree
        ]
    }


@pytest.mark.asyncio
async def test_exec_transaction_one_disagreement():
    """
    Scenario: first round is disagreement, second round is agreement
    Tests that consensus algorithm correctly rotates the leader when majority of nodes disagree
    """

    transaction = Transaction(
        hash="transaction_hash",
        from_address="from_address",
        to_address="to_address",
        status=TransactionStatus.PENDING,
        type=TransactionType.RUN_CONTRACT,
    )

    nodes = [
        {
            "address": "address1",
            "stake": 1,
            "provider": "provider1",
            "model": "model1",
            "config": "config1",
        },
        {
            "address": "address2",
            "stake": 2,
            "provider": "provider2",
            "model": "model2",
            "config": "config2",
        },
        {
            "address": "address3",
            "stake": 3,
            "provider": "provider3",
            "model": "model3",
            "config": "config3",
        },
    ]

    created_nodes = []

    def node_factory(
        node: dict,
        mode: ExecutionMode,
        contract_snapshot: ContractSnapshot,
        receipt: Receipt | None,
        msg_handler: MessageHandler,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
    ):
        mock = Mock(Node)

        mock.validator_mode = mode
        mock.address = node["address"]
        mock.leader_receipt = receipt

        async def exec_transaction(transaction: Transaction):
            return Receipt(
                vote=(
                    Vote.AGREE
                    if ((len(created_nodes) - 1) // len(nodes))
                    == 1  # only agree in the second round
                    else Vote.DISAGREE
                ),
                result=DEFAULT_EXEC_RESULT,
                calldata=b"",
                mode=mode,
                gas_used=0,
                contract_state={},
                node_config={},
                eq_outputs={},
                execution_result=ExecutionResultStatus.SUCCESS,
            )

        mock.exec_transaction.side_effect = exec_transaction

        created_nodes.append(mock)

        return mock

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory,
    )

    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": [
            TransactionStatus.PROPOSING,  # leader 1
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.PROPOSING,  # rotation, leader 2
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.ACCEPTED,
            TransactionStatus.FINALIZED,
        ]
    }

    assert len(created_nodes) == len(nodes) * 2

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)


def test_rotate():
    input = [1, 2, 3, 4, 5]
    iterator = rotate(input)

    assert next(iterator) == [1, 2, 3, 4, 5]
    assert next(iterator) == [2, 3, 4, 5, 1]
    assert next(iterator) == [3, 4, 5, 1, 2]
    assert next(iterator) == [4, 5, 1, 2, 3]
    assert next(iterator) == [5, 1, 2, 3, 4]

    with pytest.raises(StopIteration):
        next(iterator)
