from unittest.mock import Mock
import time
import pytest
from backend.consensus.base import ConsensusAlgorithm, rotate
from backend.database_handler.models import TransactionStatus
from backend.node.types import Vote
from backend.protocol_rpc.message_handler.base import MessageHandler
from tests.unit.consensus.test_helpers import (
    AccountsManagerMock,
    TransactionsProcessorMock,
    SnapshotMock,
    transaction_to_dict,
    contract_snapshot_factory,
    init_dummy_transaction,
    get_nodes_specs,
    managed_thread,
    node_factory,
    DEFAULT_FINALITY_WINDOW,
)


@pytest.mark.asyncio
async def test_exec_transaction(managed_thread):
    """
    Minor smoke checks for the happy path of a transaction execution
    """

    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(3)

    created_nodes = []

    def get_vote():
        return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    consensus = ConsensusAlgorithm(None, msg_handler_mock)

    thread_appeal = managed_thread(transactions_processor, consensus)

    await consensus.exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=lambda node, mode, contract_snapshot, receipt, msg_handler, contract_snapshot_factory: created_nodes.append(
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
        or created_nodes[-1],
    )

    assert len(created_nodes) == len(nodes)

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

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

    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(3)

    created_nodes = []

    def get_vote():
        return Vote.DISAGREE

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
        node_factory=lambda node, mode, contract_snapshot, receipt, msg_handler, contract_snapshot_factory: created_nodes.append(
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
        or created_nodes[-1],
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
async def test_exec_transaction_one_disagreement(managed_thread):
    """
    Scenario: first round is disagreement, second round is agreement
    Tests that consensus algorithm correctly rotates the leader when majority of nodes disagree
    """

    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(3)

    created_nodes = []

    def get_vote():
        return (
            Vote.AGREE
            if ((len(created_nodes) - 1) // len(nodes))
            == 1  # only agree in the second round
            else Vote.DISAGREE
        )

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    consensus = ConsensusAlgorithm(None, msg_handler_mock)

    thread_appeal = managed_thread(transactions_processor, consensus)

    await consensus.exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=lambda node, mode, contract_snapshot, receipt, msg_handler, contract_snapshot_factory: created_nodes.append(
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
        or created_nodes[-1],
    )

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

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


@pytest.mark.asyncio
async def test_exec_appeal(managed_thread):
    """
    Check making an appeal
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(3)

    created_nodes = []

    def get_vote():
        return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

    consensus = ConsensusAlgorithm(None, msg_handler_mock)

    thread_appeal = managed_thread(transactions_processor, consensus)

    await consensus.exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=lambda node, mode, contract_snapshot, receipt, msg_handler, contract_snapshot_factory: created_nodes.append(
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
        or created_nodes[-1],
    )

    assert len(created_nodes) == len(nodes)

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED
    )
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == False
    )

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    time.sleep(2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED
    )

    transactions_processor.set_transaction_appeal(transaction.hash, True)
    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["appealed"]
        == True
    )

    time.sleep(DEFAULT_FINALITY_WINDOW + 6)

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
            TransactionStatus.COMMITTING,
            TransactionStatus.REVEALING,
            TransactionStatus.ACCEPTED,
            TransactionStatus.FINALIZED,
        ]
    }

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)[
            "timestamp_accepted"
        ]
        > timestamp_accepted_1
    )
