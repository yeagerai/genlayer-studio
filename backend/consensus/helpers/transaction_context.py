from typing import Callable, Iterator
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.types import ConsensusData
from backend.domain.types import (
    Transaction,
)
from backend.node.base import Node
from backend.node.types import (
    ExecutionMode,
    Receipt,
)
from backend.protocol_rpc.message_handler.base import MessageHandler


class TransactionContext:
    """
    Class representing the context of a transaction.

    Attributes:
        transaction (Transaction): The transaction.
        transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
        chain_snapshot (ChainSnapshot): Snapshot of the chain state.
        accounts_manager (AccountsManager): Manager for accounts.
        contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
        node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        msg_handler (MessageHandler): Handler for messaging.
        consensus_data (ConsensusData): Data related to the consensus process.
        iterator_rotation (Iterator[list] | None): Iterator for rotating validators.
        remaining_validators (list): List of remaining validators.
        num_validators (int): Number of validators.
        contract_snapshot (ContractSnapshot | None): Snapshot of the contract state.
        votes (dict): Dictionary of votes.
        validator_nodes (list): List of validator nodes.
        validation_results (list): List of validation results.
    """

    def __init__(
        self,
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
        accounts_manager: AccountsManager,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
        node_factory: Callable[
            [
                dict,
                ExecutionMode,
                ContractSnapshot,
                Receipt | None,
                MessageHandler,
                Callable[[str], ContractSnapshot],
            ],
            Node,
        ],
        msg_handler: MessageHandler,
    ):
        """
        Initialize the TransactionContext.

        Args:
            transaction (Transaction): The transaction.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
            msg_handler (MessageHandler): Handler for messaging.
        """
        self.transaction = transaction
        self.transactions_processor = transactions_processor
        self.chain_snapshot = chain_snapshot
        self.accounts_manager = accounts_manager
        self.contract_snapshot_factory = contract_snapshot_factory
        self.node_factory = node_factory
        self.msg_handler = msg_handler
        self.consensus_data = ConsensusData(
            votes={}, leader_receipt=None, validators=[]
        )
        self.involved_validators: list[dict] = []
        self.remaining_validators: list = []
        self.num_validators: int = 0
        self.contract_snapshot_supplier: Callable[[], ContractSnapshot] | None = None
        self.votes: dict = {}
        self.validator_nodes: list = []
        self.validation_results: list = []
        self.rotation_count: int = 0
