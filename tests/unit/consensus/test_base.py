from unittest.mock import Mock
import time
import pytest

from backend.consensus.base import (
    ConsensusAlgorithm,
    rotate,
    DEFAULT_VALIDATORS_COUNT,
)
from backend.database_handler.models import TransactionStatus
from backend.domain.types import Transaction
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
    appeal,
    check_validator_count,
    get_leader_address,
    get_validator_addresses,
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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    assert len(created_nodes) == len(nodes)

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
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
async def test_exec_accepted_appeal_fail(managed_thread):
    """
    Test that a transaction can be appealed after being accepted where the appeal fails. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal
    3. The appeal is processed but fails
    4. The transaction goes back to the active state
    5. The appeal window is not reset
    6. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> COMMITTING -> REVEALING -appeal-fail-> ACCEPTED -no-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(2 * DEFAULT_VALIDATORS_COUNT + 2)

    created_nodes = []

    def get_vote():
        return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    assert len(created_nodes) == DEFAULT_VALIDATORS_COUNT

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
    )

    check_validator_count(
        transaction, transactions_processor, 2 * DEFAULT_VALIDATORS_COUNT + 2
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
    assert len(created_nodes) == 2 * DEFAULT_VALIDATORS_COUNT + 2

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)[
            "timestamp_accepted"
        ]
        == timestamp_accepted_1
    )


@pytest.mark.asyncio
async def test_exec_accepted_appeal_no_extra_validators(managed_thread):
    """
    Test that a transaction goes to finalized state when there are no extra validators to process the appeal. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal but there are no extra validators anymore
    3. The appeal is not processed and fails
    4. The transaction stays in the active state and appeal window is not reset
    5. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> -appeal-fail-> -no-new-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(DEFAULT_VALIDATORS_COUNT)

    created_nodes = []

    def get_vote():
        return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    assert len(created_nodes) == DEFAULT_VALIDATORS_COUNT

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
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

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)[
            "timestamp_accepted"
        ]
        == timestamp_accepted_1
    )


@pytest.mark.asyncio
async def test_exec_accepted_appeal_successful(managed_thread):
    """
    Test that a transaction can be appealed successfully after being accepted. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal
    3. The appeal is processed successfully
    4. The transaction goes back to the pending state
    5. The consensus algorithm removed the old leader
    6. The consensus algorithm goes through committing and revealing states with an increased number of validators
    7. The transaction is in the accepted state with an updated appeal window
    8. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -no-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(2 * DEFAULT_VALIDATORS_COUNT + 2)

    created_nodes = []

    def get_vote():
        """
        Leader agrees + 4 validators agree.
        Appeal: 4 validators disagree + 3 validators agree. So appeal succeeds.
        """
        if len(created_nodes) < 5:
            return Vote.AGREE
        elif (len(created_nodes) >= 5) and (len(created_nodes) < 5 + 4):
            return Vote.DISAGREE
        else:
            return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    expected_nb_created_nodes = DEFAULT_VALIDATORS_COUNT
    assert len(created_nodes) == expected_nb_created_nodes

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history = [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += expected_nb_created_nodes + 2
    assert len(created_nodes) == expected_nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    old_leader_address = get_leader_address(transaction, transactions_processor)

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
    )

    expected_nb_created_nodes += expected_nb_created_nodes - 1
    assert len(created_nodes) == expected_nb_created_nodes

    transaction_status_history += [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
        TransactionStatus.FINALIZED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)[
            "timestamp_accepted"
        ]
        > timestamp_accepted_1
    )

    check_validator_count(
        transaction, transactions_processor, 2 * DEFAULT_VALIDATORS_COUNT + 1
    )

    new_leader_address = get_leader_address(transaction, transactions_processor)

    assert new_leader_address != old_leader_address
    assert new_leader_address in validator_set_addresses


@pytest.mark.asyncio
async def test_exec_accepted_appeal_successful_rotations_undetermined(managed_thread):
    """
    Test that a transaction can do the rotations when going back to pending after being successful in its appeal. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal
    3. The appeal is processed successfully and the transaction goes back to the pending state
    4. Perform all rotation until transaction is undetermined
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> (PROPOSING -> COMMITTING -> REVEALING) * 11 -> UNDERTERMINED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(2 * DEFAULT_VALIDATORS_COUNT + 2)

    created_nodes = []

    def get_vote():
        """
        Leader agrees + 4 validators agree.
        Appeal: 7 validators disagree. So appeal succeeds.
        Rotations: 11 validator disagree.
        """
        if len(created_nodes) < 5:
            return Vote.AGREE
        else:
            return Vote.DISAGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    expected_nb_created_nodes = DEFAULT_VALIDATORS_COUNT
    assert len(created_nodes) == expected_nb_created_nodes

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history = [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += expected_nb_created_nodes + 2
    assert len(created_nodes) == expected_nb_created_nodes

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.UNDETERMINED.value
    )

    transaction_status_history += [
        *(
            [
                TransactionStatus.PROPOSING,
                TransactionStatus.COMMITTING,
                TransactionStatus.REVEALING,
            ]
            * 11
        ),
        TransactionStatus.UNDETERMINED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    check_validator_count(
        transaction, transactions_processor, 2 * DEFAULT_VALIDATORS_COUNT + 1
    )


@pytest.mark.asyncio
async def test_exec_accepted_appeal_successful_twice(managed_thread):
    """
    Test that a transaction can be appealed successfully twice after being accepted. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal
    3. The appeal is processed successfully
    4. The transaction goes back to the pending state
    5. The consensus algorithm removed the old leader
    6. The consensus algorithm goes through committing and revealing states with an increased number of validators
    7. The transaction is in the accepted state with an updated appeal window
    8. Do 1-7 again
    9. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -no-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(2 * (2 * DEFAULT_VALIDATORS_COUNT + 1) + 1 + 2)

    created_nodes = []

    def get_vote():
        """
        Normal: Leader agrees + 4 validators agree.
        Appeal: 7 validators disagree. So appeal succeeds.
        Normal: Leader agrees + 10 validators agree.
        Appeal: 13 validators disagree. So appeal succeeds.
        Normal: Leader agrees + 22 validators agree.
        """
        if len(created_nodes) < 5:
            return Vote.AGREE
        elif (len(created_nodes) >= 5) and (len(created_nodes) < 5 + 7):
            return Vote.DISAGREE
        elif (len(created_nodes) >= 5 + 7) and (len(created_nodes) < 5 + 7 + 11):
            return Vote.AGREE
        elif (len(created_nodes) >= 5 + 7 + 11) and (
            len(created_nodes) < 5 + 7 + 11 + 13
        ):
            return Vote.DISAGREE
        else:
            return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    expected_nb_created_nodes = DEFAULT_VALIDATORS_COUNT  # 5
    assert len(created_nodes) == expected_nb_created_nodes

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    transaction_status_history = [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history += [
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += DEFAULT_VALIDATORS_COUNT + 2  # 5 + 7 = 12
    assert len(created_nodes) == expected_nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    old_leader_address = get_leader_address(transaction, transactions_processor)

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    transaction_status_history += [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += 2 * DEFAULT_VALIDATORS_COUNT + 1  # 12 + 11 = 23
    assert len(created_nodes) == expected_nb_created_nodes

    timestamp_accepted_2 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]
    assert timestamp_accepted_2 > timestamp_accepted_1

    check_validator_count(
        transaction, transactions_processor, 2 * DEFAULT_VALIDATORS_COUNT + 1
    )

    new_leader_address = get_leader_address(transaction, transactions_processor)

    assert new_leader_address != old_leader_address
    assert new_leader_address in validator_set_addresses

    appeal(transaction, transactions_processor)

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history += [
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += (2 * DEFAULT_VALIDATORS_COUNT + 1) + 2  # 23 + 13 = 36
    assert len(created_nodes) == expected_nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    old_leader_address = get_leader_address(transaction, transactions_processor)

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
    )

    transaction_status_history += [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
        TransactionStatus.FINALIZED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += (
        2 * (2 * DEFAULT_VALIDATORS_COUNT + 1) + 2
    ) - 1  # 36 + 23 = 58
    assert len(created_nodes) == expected_nb_created_nodes

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)[
            "timestamp_accepted"
        ]
        > timestamp_accepted_2
    )

    check_validator_count(
        transaction, transactions_processor, 2 * (2 * DEFAULT_VALIDATORS_COUNT + 1) + 1
    )

    new_leader_address = get_leader_address(transaction, transactions_processor)

    assert new_leader_address != old_leader_address
    assert new_leader_address in validator_set_addresses


@pytest.mark.asyncio
async def test_exec_accepted_appeal_fail_three_times(managed_thread):
    """
    Test that a transaction can be appealed after being accepted where the appeal fails three times. This verifies that:
    1. The transaction can enter appeal state after being accepted
    2. New validators are selected to process the appeal:
        2.1 N+2 new validators where appeal_failed = 0
        2.2 N+2 old validators from 2.1 + N+1 new validators = 2N+3 validators where appeal_failed = 1
        2.3 2N+3 old validators from 2.2 + 2N new validators = 4N+3 validators where appeal_failed = 2
        2.4 No need to continue testing more validators as it follows the same pattern as 2.3 calculation
    3. The appeal is processed but fails
    4. The transaction goes back to the active state
    5. The appeal window is not reset
    6. Redo 1-5 two more times to check if the correct amount of validators are selected. First time takes 2.2 validators, second time takes 2.3 validators.
    7. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED (-appeal-> COMMITTING -> REVEALING -appeal-fail-> ACCEPTED)x3 -no-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(5 * DEFAULT_VALIDATORS_COUNT + 3)

    created_nodes = []

    def get_vote():
        return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    n = DEFAULT_VALIDATORS_COUNT
    nb_validators_processing_appeal = n
    nb_created_nodes = n

    check_validator_count(
        transaction, transactions_processor, nb_validators_processing_appeal
    )

    assert len(created_nodes) == nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    leader_address = get_leader_address(transaction, transactions_processor)

    for appeal_failed in range(3):
        assert (
            transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
            == TransactionStatus.ACCEPTED.value
        )

        appeal(transaction, transactions_processor)

        time.sleep(1.5)

        assert (
            transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
            == TransactionStatus.ACCEPTED.value
        )

        assert (
            transactions_processor.get_transaction_by_hash(transaction.hash)[
                "timestamp_accepted"
            ]
            == timestamp_accepted_1
        )

        if appeal_failed == 0:
            nb_validators_processing_appeal += n + 2
        elif appeal_failed == 1:
            nb_validators_processing_appeal += n + 1
        else:
            nb_validators_processing_appeal += 2 * n  # 5, 12, 18, 28

        nb_created_nodes += (
            nb_validators_processing_appeal - n
        )  # 5, 7, 13, 23 -> 5, 12, 25, 48

        assert (
            transactions_processor.get_transaction_by_hash(transaction.hash)[
                "appeal_failed"
            ]
            == appeal_failed + 1
        )

        check_validator_count(
            transaction, transactions_processor, nb_validators_processing_appeal
        )

        assert len(created_nodes) == nb_created_nodes

        validator_set_addresses_old = validator_set_addresses
        validator_set_addresses = get_validator_addresses(
            transaction, transactions_processor
        )
        assert validator_set_addresses_old != validator_set_addresses
        assert validator_set_addresses_old.issubset(validator_set_addresses)
        assert leader_address == get_leader_address(transaction, transactions_processor)
        assert leader_address not in validator_set_addresses

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
    )

    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": [
            TransactionStatus.PROPOSING,
            *(
                [
                    TransactionStatus.COMMITTING,
                    TransactionStatus.REVEALING,
                    TransactionStatus.ACCEPTED,
                ]
                * 4
            ),
            TransactionStatus.FINALIZED,
        ]
    }


@pytest.mark.asyncio
async def test_exec_accepted_appeal_successful_fail_successful(managed_thread):
    """
    Test that a transaction can be appealed successfully, then appeal fails, then be successfully appealed again after being accepted. This verifies that:
    1. The transaction can enter appeal state
    2. New validators are selected to process the appeal
    3. The appeal is processed successfully
    4. The transaction goes back to the pending state
    5. The consensus algorithm removes the old leader
    6. The consensus algorithm goes through committing and revealing states with an increased number of validators
    7. The transaction is in the accepted state with an updated appeal window
    8. The transaction can enter appeal state
    9. New validators are selected to process the appeal
    10. The appeal is processed but fails
    11. The transaction goes back to the active state
    12. The appeal window is not reset
    13. Redo 1-7
    14. The transaction is finalized after the appeal window
    The states the transaction goes through are:
        PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED
        -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED ->
        -appeal-> COMMITTING -> REVEALING -appeal-fail-> ACCEPTED
        -appeal-> COMMITTING -> REVEALING -appeal-success->
        PENDING -> PROPOSING -> COMMITTING -> REVEALING -> ACCEPTED -> -no-appeal-> FINALIZED
    """
    transaction = init_dummy_transaction()

    nodes = get_nodes_specs(37)

    created_nodes = []

    def get_vote():
        """
        Leader agrees + 4 validators agree.
        Appeal: 7 validators disagree. So appeal succeeds.
        Leader agrees + 10 validators agree.
        Appeal: 13 validators agree. So appeal fails.
        Appeal: 25 validators disagree. So appeal succeeds.
        Leader agrees + 34 validators agree.
        """
        if len(created_nodes) < 5:
            return Vote.AGREE
        elif (len(created_nodes) >= 5) and (len(created_nodes) < 5 + 7):
            return Vote.DISAGREE
        elif (len(created_nodes) >= 5 + 7) and (len(created_nodes) < 5 + 7 + 11 + 13):
            return Vote.AGREE
        elif (len(created_nodes) >= 5 + 7 + 11 + 13) and (
            len(created_nodes) < 5 + 7 + 11 + 13 + 25
        ):
            return Vote.DISAGREE
        else:
            return Vote.AGREE

    transactions_processor = TransactionsProcessorMock(
        [transaction_to_dict(transaction)]
    )

    msg_handler_mock = Mock(MessageHandler)

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

    managed_thread(
        transactions_processor, msg_handler_mock, nodes, node_factory_supplier
    )

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    expected_nb_created_nodes = DEFAULT_VALIDATORS_COUNT
    assert len(created_nodes) == expected_nb_created_nodes

    for node in created_nodes:
        node.exec_transaction.assert_awaited_once_with(transaction)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    transaction_status_history = [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    # Appeal successful
    timestamp_accepted_1 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    appeal(transaction, transactions_processor)

    time.sleep(2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history += [
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += expected_nb_created_nodes + 2
    assert len(created_nodes) == expected_nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    old_leader_address = get_leader_address(transaction, transactions_processor)

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    time.sleep(2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    transaction_status_history += [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    n_new = expected_nb_created_nodes - 1
    expected_nb_created_nodes += n_new
    assert len(created_nodes) == expected_nb_created_nodes

    timestamp_accepted_2 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    assert timestamp_accepted_2 > timestamp_accepted_1

    check_validator_count(transaction, transactions_processor, n_new)

    new_leader_address = get_leader_address(transaction, transactions_processor)

    assert new_leader_address != old_leader_address
    assert new_leader_address in validator_set_addresses

    # Appeal fails
    appeal(transaction, transactions_processor)

    time.sleep(2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.ACCEPTED.value
    )

    transaction_status_history += [
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += n_new + 2
    assert len(created_nodes) == expected_nb_created_nodes

    check_validator_count(transaction, transactions_processor, 2 * n_new + 2)

    timestamp_accepted_3 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    assert timestamp_accepted_3 == timestamp_accepted_2

    validator_set_addresses_after_appeal_fail = get_validator_addresses(
        transaction, transactions_processor
    )

    # Appeal successful
    appeal(transaction, transactions_processor)

    time.sleep(2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.PENDING.value
    )

    transaction_status_history += [
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.PENDING,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += 2 * n_new + 3
    assert len(created_nodes) == expected_nb_created_nodes

    validator_set_addresses = get_validator_addresses(
        transaction, transactions_processor
    )
    old_leader_address = get_leader_address(transaction, transactions_processor)

    assert validator_set_addresses_after_appeal_fail.issubset(validator_set_addresses)

    transaction = Transaction.from_dict(
        transactions_processor.get_transaction_by_hash(transaction.hash)
    )  # update the variable with the consensus data

    await ConsensusAlgorithm(None, msg_handler_mock).exec_transaction(
        transaction=transaction,
        transactions_processor=transactions_processor,
        snapshot=SnapshotMock(nodes),
        accounts_manager=AccountsManagerMock(),
        contract_snapshot_factory=contract_snapshot_factory,
        node_factory=node_factory_supplier,
    )

    time.sleep(DEFAULT_FINALITY_WINDOW + 2)

    assert (
        transactions_processor.get_transaction_by_hash(transaction.hash)["status"]
        == TransactionStatus.FINALIZED.value
    )

    transaction_status_history += [
        TransactionStatus.PROPOSING,
        TransactionStatus.COMMITTING,
        TransactionStatus.REVEALING,
        TransactionStatus.ACCEPTED,
        TransactionStatus.FINALIZED,
    ]
    assert transactions_processor.updated_transaction_status_history == {
        "transaction_hash": transaction_status_history
    }

    expected_nb_created_nodes += 3 * n_new + 2
    assert len(created_nodes) == expected_nb_created_nodes

    timestamp_accepted_4 = transactions_processor.get_transaction_by_hash(
        transaction.hash
    )["timestamp_accepted"]

    assert timestamp_accepted_4 > timestamp_accepted_3

    check_validator_count(transaction, transactions_processor, 3 * n_new + 2)

    new_leader_address = get_leader_address(transaction, transactions_processor)

    assert new_leader_address != old_leader_address
    assert new_leader_address in validator_set_addresses
