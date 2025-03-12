# backend/consensus/base.py

DEFAULT_VALIDATORS_COUNT = 5
DEFAULT_CONSENSUS_SLEEP_TIME = 5

from typing import Callable, List, Iterable, Literal
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session
from backend.consensus.vrf import get_validators_for_transaction
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.types import ConsensusData
from backend.domain.types import (
    Transaction,
    TransactionType,
    LLMProvider,
    Validator,
)
from backend.node.base import Node
from backend.node.types import (
    ExecutionMode,
    Receipt,
    PendingTransaction,
)
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.message_handler.types import (
    LogEvent,
    EventType,
    EventScope,
)
from backend.consensus.helpers.transaction_context import TransactionContext


def node_factory(
    validator: dict,
    validator_mode: ExecutionMode,
    contract_snapshot: ContractSnapshot,
    leader_receipt: Receipt | None,
    msg_handler: MessageHandler,
    contract_snapshot_factory: Callable[[str], ContractSnapshot],
) -> Node:
    """
    Factory function to create a Node instance.

    Args:
        validator (dict): Validator information.
        validator_mode (ExecutionMode): Mode of execution for the validator.
        contract_snapshot (ContractSnapshot): Snapshot of the contract state.
        leader_receipt (Receipt | None): Receipt of the leader node.
        msg_handler (MessageHandler): Handler for messaging.
        contract_snapshot_factory (Callable[[str], ContractSnapshot]): Factory function to create contract snapshots.

    Returns:
        Node: A new Node instance.
    """
    # Create a node instance with the provided parameters
    return Node(
        contract_snapshot=contract_snapshot,
        validator_mode=validator_mode,
        leader_receipt=leader_receipt,
        msg_handler=msg_handler,
        validator=Validator(
            address=validator["address"],
            stake=validator["stake"],
            llmprovider=LLMProvider(
                provider=validator["provider"],
                model=validator["model"],
                config=validator["config"],
                plugin=validator["plugin"],
                plugin_config=validator["plugin_config"],
            ),
        ),
        contract_snapshot_factory=contract_snapshot_factory,
    )


def contract_snapshot_factory(
    contract_address: str,
    session: Session,
    transaction: Transaction,
):
    """
    Factory function to create a ContractSnapshot instance.

    Args:
        contract_address (str): The address of the contract.
        session (Session): The database session.
        transaction (Transaction): The transaction related to the contract.

    Returns:
        ContractSnapshot: A new ContractSnapshot instance.
    """
    # Check if the transaction is a contract deployment and the contract address matches the transaction's to address
    if (
        transaction.type == TransactionType.DEPLOY_CONTRACT
        and contract_address == transaction.to_address
        and transaction.status != TransactionStatus.ACCEPTED
    ):
        # Create a new ContractSnapshot instance for the new contract
        ret = ContractSnapshot(None, session)
        ret.contract_address = transaction.to_address
        ret.contract_code = transaction.data["contract_code"]
        ret.balance = transaction.value or 0
        ret.states = {"accepted": {}, "finalized": {}}
        ret.encoded_state = ret.states["accepted"]
        ret.ghost_contract_address = transaction.ghost_contract_address
        return ret

    # Return a ContractSnapshot instance for an existing contract
    return ContractSnapshot(contract_address, session)


def chain_snapshot_factory(session: Session):
    """
    Factory function to create a ChainSnapshot instance.

    Args:
        session (Session): The database session.

    Returns:
        ChainSnapshot: A new ChainSnapshot instance.
    """
    return ChainSnapshot(session)


def transactions_processor_factory(session: Session):
    """
    Factory function to create a TransactionsProcessor instance.

    Args:
        session (Session): The database session.

    Returns:
        TransactionsProcessor: A new TransactionsProcessor instance.
    """
    return TransactionsProcessor(session)


def accounts_manager_factory(session: Session):
    """
    Factory function to create an AccountsManager instance.

    Args:
        session (Session): The database session.

    Returns:
        AccountsManager: A new AccountsManager instance.
    """
    return AccountsManager(session)


# Common consensus helper functions
def dispatch_transaction_status_update(
    transactions_processor: TransactionsProcessor,
    transaction_hash: str,
    new_status: TransactionStatus,
    msg_handler: MessageHandler,
):
    """
    Dispatch a transaction status update.

    Args:
        transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
        transaction_hash (str): Hash of the transaction.
        new_status (TransactionStatus): New status of the transaction.
        msg_handler (MessageHandler): Handler for messaging.
    """
    # Update the transaction status in the transactions processor
    transactions_processor.update_transaction_status(transaction_hash, new_status)

    # Send a message indicating the transaction status update
    msg_handler.send_message(
        LogEvent(
            "transaction_status_updated",
            EventType.INFO,
            EventScope.CONSENSUS,
            f"{str(new_status.value)} {str(transaction_hash)}",
            {
                "hash": str(transaction_hash),
                "new_status": str(new_status.value),
            },
            transaction_hash=transaction_hash,
        )
    )


def get_validators_from_consensus_data(
    all_validators: List[dict], consensus_data: ConsensusData, include_leader: bool
):
    """
    Get validators from consensus data.

    Args:
        all_validators (List[dict]): List of all validators.
        consensus_data (ConsensusData): Data related to the consensus process.
        include_leader (bool): Whether to get the leader in the validator set.
    Returns:
        list: List of validators involved in the consensus process (can include the leader).
        dict: Dictionary mapping addresses to validators not used in the consensus process.
    """
    # Create a dictionary to map addresses to a validator
    validator_map = {validator["address"]: validator for validator in all_validators}

    # Extract address of the leader from consensus data
    if include_leader:
        receipt_addresses = [consensus_data.leader_receipt.node_config["address"]]
    else:
        receipt_addresses = []

    # Extract addresses of validators from consensus data
    receipt_addresses += [
        receipt.node_config["address"] for receipt in consensus_data.validators
    ]

    # Return validators whose addresses are in the receipt addresses
    validators = [
        validator_map.pop(receipt_address)
        for receipt_address in receipt_addresses
        if receipt_address in validator_map
    ]

    return validators, validator_map


def get_used_leader_addresses_from_consensus_history(
    consensus_history: dict, current_leader_receipt: Receipt | None = None
):
    """
    Get the used leader addresses from the consensus history.

    Args:
        consensus_history (dict): Dictionary of consensus rounds results and status changes.
        current_leader_receipt (Receipt | None): Current leader receipt.

    Returns:
        set[str]: Set of used leader addresses.
    """
    used_leader_addresses = set()
    if "consensus_results" in consensus_history:
        for consensus_round in consensus_history["consensus_results"]:
            leader_receipt = consensus_round["leader_result"]
            if leader_receipt:
                used_leader_addresses.update([leader_receipt["node_config"]["address"]])

    # consensus_history does not contain the latest consensus_data
    if current_leader_receipt:
        used_leader_addresses.update([current_leader_receipt.node_config["address"]])

    return used_leader_addresses


def get_extra_validators(
    all_validators: List[dict],
    consensus_history: dict,
    consensus_data: ConsensusData,
    appeal_failed: int,
):
    """
    Get extra validators for the appeal process according to the following formula:
    - when appeal_failed = 0, add n + 2 validators
    - when appeal_failed > 0, add (2 * appeal_failed * n + 1) + 2 validators
    Note that for appeal_failed > 0, the returned set contains the old validators
    from the previous appeal round and new validators.

    Args:
        all_validators (List[dict]): List of all validators.
        consensus_history (dict): Dictionary of consensus rounds results and status changes.
        consensus_data (ConsensusData): Data related to the consensus process.
        appeal_failed (int): Number of times the appeal has failed.

    Returns:
        list: List of current validators.
        list: List of extra validators.
    """
    # Get current validators and a dictionary mapping addresses to validators not used in the consensus process
    current_validators, validator_map = get_validators_from_consensus_data(
        all_validators, consensus_data, False
    )

    # Remove used leaders from validator_map
    used_leader_addresses = get_used_leader_addresses_from_consensus_history(
        consensus_history
    )
    for used_leader_address in used_leader_addresses:
        if used_leader_address in validator_map:
            validator_map.pop(used_leader_address)

    # Set not_used_validators to the remaining validators in validator_map
    not_used_validators = list(validator_map.values())

    if len(not_used_validators) == 0:
        raise ValueError("No validators found")

    nb_current_validators = len(current_validators) + 1  # including the leader
    if appeal_failed == 0:
        # Calculate extra validators when no appeal has failed
        extra_validators = get_validators_for_transaction(
            not_used_validators, nb_current_validators + 2
        )
    elif appeal_failed == 1:
        # Calculate extra validators when one appeal has failed
        n = (nb_current_validators - 2) // 2
        extra_validators = get_validators_for_transaction(not_used_validators, n + 1)
        extra_validators = current_validators[n - 1 :] + extra_validators
    else:
        # Calculate extra validators when more than one appeal has failed
        n = (nb_current_validators - 3) // (2 * appeal_failed - 1)
        extra_validators = get_validators_for_transaction(not_used_validators, 2 * n)
        extra_validators = current_validators[n - 1 :] + extra_validators

    return current_validators, extra_validators


def execute_transfer(
    transaction: Transaction,
    transactions_processor: TransactionsProcessor,
    accounts_manager: AccountsManager,
    msg_handler: MessageHandler,
):
    """
    Executes a native token transfer between Externally Owned Accounts (EOAs).

    This function handles the transfer of native tokens from one EOA to another.
    It updates the balances of both the sender and recipient accounts, and
    manages the transaction status throughout the process.

    Args:
        transaction (dict): The transaction details including from_address, to_address, and value.
        transactions_processor (TransactionsProcessor): Instance responsible for handling transaction operations within the database.
        accounts_manager (AccountsManager): Manager to handle account balance updates.
        msg_handler (MessageHandler): Handler for messaging.
    """
    # Check if the transaction is a fund_account call
    if not transaction.from_address is None:
        # Get the balance of the sender account
        from_balance = accounts_manager.get_account_balance(transaction.from_address)

        # Check if the sender has enough balance
        if from_balance < transaction.value:
            # Set the transaction status to UNDETERMINED if balance is insufficient
            dispatch_transaction_status_update(
                transactions_processor,
                transaction.hash,
                TransactionStatus.UNDETERMINED,
                msg_handler,
            )

            transactions_processor.create_rollup_transaction(transaction.hash)
            return

        # Update the balance of the sender account
        accounts_manager.update_account_balance(
            transaction.from_address, from_balance - transaction.value
        )

    # Check if the transaction is a burn call
    if not transaction.to_address is None:
        # Get the balance of the recipient account
        to_balance = accounts_manager.get_account_balance(transaction.to_address)

        # Update the balance of the recipient account
        accounts_manager.update_account_balance(
            transaction.to_address, to_balance + transaction.value
        )

    # Dispatch a transaction status update to FINALIZED
    dispatch_transaction_status_update(
        transactions_processor,
        transaction.hash,
        TransactionStatus.FINALIZED,
        msg_handler,
    )

    transactions_processor.create_rollup_transaction(transaction.hash)


class TransactionState(ABC):
    """
    Abstract base class representing a state in the transaction process.
    """

    @abstractmethod
    async def handle(self, context: TransactionContext):
        """
        Handle the state transition.

        Args:
            context (TransactionContext): The context of the transaction.
        """
        pass


def _emit_transactions(
    context: TransactionContext,
    pending_transactions: Iterable[PendingTransaction],
    on: Literal["accepted", "finalized"],
):
    for pending_transaction in filter(lambda t: t.on == on, pending_transactions):
        nonce = context.transactions_processor.get_transaction_count(
            context.transaction.to_address
        )
        data: dict
        transaction_type: TransactionType
        if pending_transaction.is_deploy():
            transaction_type = TransactionType.DEPLOY_CONTRACT
            new_contract_address: str
            if pending_transaction.salt_nonce == 0:
                # NOTE: this address is random, which doesn't 100% align with consensus spec
                new_contract_address = (
                    context.accounts_manager.create_new_account().address
                )
            else:
                from eth_utils.crypto import keccak
                from backend.node.types import Address
                from backend.node.base import SIMULATOR_CHAIN_ID

                arr = bytearray()
                arr.append(1)
                arr.extend(Address(context.transaction.to_address).as_bytes)
                arr.extend(
                    pending_transaction.salt_nonce.to_bytes(32, "big", signed=False)
                )
                arr.extend(SIMULATOR_CHAIN_ID.to_bytes(32, "big", signed=False))
                new_contract_address = Address(keccak(arr)[:20]).as_hex
                context.accounts_manager.create_new_account_with_address(
                    new_contract_address
                )
            pending_transaction.address = new_contract_address
            data = {
                "contract_address": new_contract_address,
                "contract_code": pending_transaction.code,
                "calldata": pending_transaction.calldata,
            }
        else:
            transaction_type = TransactionType.RUN_CONTRACT
            data = {
                "calldata": pending_transaction.calldata,
            }
        context.transactions_processor.insert_transaction(
            context.transaction.to_address,  # new calls are done by the contract
            pending_transaction.address,
            data,
            value=0,  # we only handle EOA transfers at the moment, so no value gets transferred
            type=transaction_type.value,
            nonce=nonce,
            leader_only=context.transaction.leader_only,  # Cascade
            triggered_by_hash=context.transaction.hash,
        )
