import time
from typing import List, Dict, Callable
from backend.domain.types import Transaction
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.contract_processor import ContractProcessor
from backend.database_handler.accounts_manager import AccountsManager
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.finalizing_state import FinalizingState
from backend.rollup.consensus_service import ConsensusService


class FinalizationProcessor:
    @staticmethod
    async def process_finalization(
        transaction: Transaction,
        transactions_processor: TransactionsProcessor,
        chain_snapshot: ChainSnapshot,
        accounts_manager: AccountsManager,
        contract_snapshot_factory: Callable[[str], ContractSnapshot],
        contract_processor: ContractProcessor,
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
        consensus_service: ConsensusService,
    ):
        """
        Process the finalization of a transaction.

        Args:
            transaction (Transaction): The transaction to finalize.
            transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
            chain_snapshot (ChainSnapshot): Snapshot of the chain state.
            accounts_manager (AccountsManager): Manager for accounts.
            contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.
            node_factory (Callable[[dict, ExecutionMode, ContractSnapshot, Receipt | None, MessageHandler, Callable[[str], ContractSnapshot]], Node]): Factory function to create nodes.
        """
        # Create a transaction context for finalizing the transaction
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            contract_processor=contract_processor,
            node_factory=node_factory,
            msg_handler=msg_handler,
            consensus_service=consensus_service,
        )

        state = FinalizingState()
        await state.handle(context)

    @staticmethod
    def can_finalize_transaction(
        transactions_processor: TransactionsProcessor,
        transaction: Transaction,
        index: int,
        accepted_undetermined_queue: list[dict],
        finality_window_time: int,
        finality_window_appeal_failed_reduction: float,
    ) -> bool:
        """
        Check if the transaction can be finalized based on the following criteria:
        - The transaction is a leader only transaction
        - The transaction has exceeded the finality window
        - The previous transaction has been finalized

        Args:
            transactions_processor (TransactionsProcessor): The transactions processor instance.
            transaction (Transaction): The transaction to be possibly finalized.
            index (int): The index of the current transaction in the accepted_undetermined_queue.
            accepted_undetermined_queue (list[dict]): The list of accepted and undetermined transactions for one contract.

        Returns:
            bool: True if the transaction can be finalized, False otherwise.
        """
        if (transaction.leader_only) or (
            (
                time.time()
                - transaction.timestamp_awaiting_finalization
                - transaction.appeal_processing_time
            )
            > finality_window_time
            * (
                (1 - finality_window_appeal_failed_reduction)
                ** transaction.appeal_failed
            )
        ):
            if index == 0:
                return True
            else:
                previous_transaction_hash = accepted_undetermined_queue[index - 1][
                    "hash"
                ]
                previous_transaction = transactions_processor.get_transaction_by_hash(
                    previous_transaction_hash
                )
                if previous_transaction["status"] == TransactionStatus.FINALIZED.value:
                    return True
                else:
                    return False
        else:
            return False
