import time
from typing import List, Dict, Callable
from backend.domain.types import Transaction
from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.accounts_manager import AccountsManager
from backend.node.base import Node
from backend.node.types import ExecutionMode, Receipt
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.consensus.helpers.transaction_context import TransactionContext
from backend.consensus.states.finalizing_state import FinalizingState


class FinalizationProcessor:
    @staticmethod
    async def process_finalization(
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
        """Process the finalization of a transaction."""
        context = TransactionContext(
            transaction=transaction,
            transactions_processor=transactions_processor,
            chain_snapshot=chain_snapshot,
            accounts_manager=accounts_manager,
            contract_snapshot_factory=contract_snapshot_factory,
            node_factory=node_factory,
            msg_handler=msg_handler,
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
    ) -> bool:
        """
        Check if the transaction can be finalized based on the following criteria:
        - The transaction is a leader only transaction
        - The transaction has exceeded the finality window
        - The previous transaction has been finalized
        """
        if transaction.leader_only or (
            (
                int(time.time())
                - transaction.timestamp_awaiting_finalization
                - transaction.appeal_processing_time
            )
            > finality_window_time
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
                if previous_transaction["status"] == "FINALIZED":
                    return True
                else:
                    return False
        else:
            return False
