from typing import Iterable, Literal

from backend.consensus.helpers.transaction_context import TransactionContext
from backend.domain.types import TransactionType
from backend.node.types import PendingTransaction


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
