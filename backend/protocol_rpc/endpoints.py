# rpc/endpoints.py
import random
import json
import eth_utils
from functools import partial, wraps
from typing import Any
from flask_jsonrpc import JSONRPC
from flask_jsonrpc.exceptions import JSONRPCError
from sqlalchemy import Table
from sqlalchemy.orm import Session

from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.llm_providers import LLMProviderRegistry
from backend.rollup.consensus_service import ConsensusService
from backend.database_handler.models import Base, TransactionStatus
from backend.domain.types import LLMProvider, Validator, TransactionType
from backend.node.create_nodes.providers import (
    get_default_provider_for,
    validate_provider,
)
from backend.llms import get_llm_plugin
from backend.protocol_rpc.message_handler.base import (
    MessageHandler,
    get_client_session_id,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.database_handler.validators_registry import ValidatorsRegistry

from backend.node.create_nodes.create_nodes import (
    random_validator_config,
)

from backend.protocol_rpc.endpoint_generator import generate_rpc_endpoint

from backend.protocol_rpc.transactions_parser import TransactionParser
from backend.errors.errors import InvalidAddressError, InvalidTransactionError

from backend.database_handler.transactions_processor import (
    TransactionAddressFilter,
    TransactionsProcessor,
)
from backend.node.base import Node, SIMULATOR_CHAIN_ID
from backend.node.types import ExecutionMode, ExecutionResultStatus, Vote
from backend.consensus.base import ConsensusAlgorithm

from flask_jsonrpc.exceptions import JSONRPCError
import base64
import os
from backend.protocol_rpc.message_handler.types import LogEvent, EventType, EventScope
from backend.protocol_rpc.types import DecodedsubmitAppealDataArgs
from backend.database_handler.snapshot_manager import SnapshotManager
from datetime import datetime
import time
from web3 import Web3
import rlp
import backend.node.genvm.origin.calldata as calldata


####### WRAPPER TO BLOCK ENDPOINTS FOR HOSTED ENVIRONMENT #######
def check_forbidden_method_in_hosted_studio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if os.getenv("VITE_IS_HOSTED") == "true":
            raise JSONRPCError(
                code=-32000,
                message="Non-allowed operation",
                data={},
            )
        return func(*args, **kwargs)

    return wrapper


####### HELPER ENDPOINTS #######
def ping() -> str:
    return "OK"


####### SIMULATOR ENDPOINTS #######
@check_forbidden_method_in_hosted_studio
def clear_db_tables(session: Session, tables: list) -> None:
    for table_name in tables:
        table = Table(
            table_name, Base.metadata, autoload=True, autoload_with=session.bind
        )
        session.execute(table.delete())


def fund_account(
    accounts_manager: AccountsManager,
    transactions_processor: TransactionsProcessor,
    account_address: str,
    amount: int,
) -> str:
    if not accounts_manager.is_valid_address(account_address):
        raise InvalidAddressError(account_address)

    nonce = transactions_processor.get_transaction_count(None)
    transaction_hash = transactions_processor.insert_transaction(
        None, account_address, None, amount, 0, nonce, False, 0
    )
    return transaction_hash


@check_forbidden_method_in_hosted_studio
def reset_defaults_llm_providers(llm_provider_registry: LLMProviderRegistry) -> None:
    llm_provider_registry.reset_defaults()


async def get_providers_and_models(
    llm_provider_registry: LLMProviderRegistry,
) -> list[dict]:
    return await llm_provider_registry.get_all_dict()


@check_forbidden_method_in_hosted_studio
def add_provider(llm_provider_registry: LLMProviderRegistry, params: dict) -> int:
    provider = LLMProvider(
        provider=params["provider"],
        model=params["model"],
        config=params["config"],
        plugin=params["plugin"],
        plugin_config=params["plugin_config"],
    )

    validate_provider(provider)

    return llm_provider_registry.add(provider)


@check_forbidden_method_in_hosted_studio
def update_provider(
    llm_provider_registry: LLMProviderRegistry, id: int, params: dict
) -> None:
    provider = LLMProvider(
        provider=params["provider"],
        model=params["model"],
        config=params["config"],
        plugin=params["plugin"],
        plugin_config=params["plugin_config"],
    )
    validate_provider(provider)

    llm_provider_registry.update(id, provider)


@check_forbidden_method_in_hosted_studio
def delete_provider(llm_provider_registry: LLMProviderRegistry, id: int) -> None:
    llm_provider_registry.delete(id)


def create_validator(
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    stake: int,
    provider: str,
    model: str,
    config: dict | None = None,
    plugin: str | None = None,
    plugin_config: dict | None = None,
) -> dict:
    # fallback for default provider
    llm_provider = None

    if config is None or plugin is None or plugin_config is None:
        llm_provider = get_default_provider_for(provider, model)
    else:
        llm_provider = LLMProvider(
            provider=provider,
            model=model,
            config=config,
            plugin=plugin,
            plugin_config=plugin_config,
        )
        validate_provider(llm_provider)

    account = accounts_manager.create_new_account()

    return validators_registry.create_validator(
        Validator(
            address=account.address,
            private_key=account.key,
            stake=stake,
            llmprovider=llm_provider,
        )
    )


@check_forbidden_method_in_hosted_studio
async def create_random_validator(
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    llm_provider_registry: LLMProviderRegistry,
    stake: int,
) -> dict:
    return (
        await create_random_validators(
            validators_registry,
            accounts_manager,
            llm_provider_registry,
            1,
            stake,
            stake,
        )
    )[0]


@check_forbidden_method_in_hosted_studio
async def create_random_validators(
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    llm_provider_registry: LLMProviderRegistry,
    count: int,
    min_stake: int,
    max_stake: int,
    limit_providers: list[str] = None,
    limit_models: list[str] = None,
) -> list[dict]:
    limit_providers = limit_providers or []
    limit_models = limit_models or []

    details = await random_validator_config(
        llm_provider_registry.get_all,
        get_llm_plugin,
        limit_providers=set(limit_providers),
        limit_models=set(limit_models),
        amount=count,
    )

    response = []
    for detail in details:
        stake = random.randint(min_stake, max_stake)
        validator_account = accounts_manager.create_new_account()

        validator = validators_registry.create_validator(
            Validator(
                address=validator_account.address,
                private_key=validator_account.key,
                stake=stake,
                llmprovider=detail,
            )
        )
        response.append(validator)

    return response


@check_forbidden_method_in_hosted_studio
def update_validator(
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    validator_address: str,
    stake: int,
    provider: str,
    model: str,
    config: dict | None = None,
    plugin: str | None = None,
    plugin_config: dict | None = None,
) -> dict:
    # Remove validation while adding migration to update the db address
    # if not accounts_manager.is_valid_address(validator_address):
    #     raise InvalidAddressError(validator_address)

    # fallback for default provider
    # TODO: only accept all or none of the config fields
    llm_provider = None
    if not (plugin and plugin_config):
        llm_provider = get_default_provider_for(provider, model)
        if config:
            llm_provider.config = config
    else:
        llm_provider = LLMProvider(
            provider=provider,
            model=model,
            config=config,
            plugin=plugin,
            plugin_config=plugin_config,
        )
        validate_provider(llm_provider)

    validator = Validator(
        address=validator_address,
        stake=stake,
        llmprovider=llm_provider,
    )
    return validators_registry.update_validator(validator)


@check_forbidden_method_in_hosted_studio
def delete_validator(
    validators_registry: ValidatorsRegistry,
    accounts_manager: AccountsManager,
    validator_address: str,
) -> str:
    # Remove validation while adding migration to update the db address
    # if not accounts_manager.is_valid_address(validator_address):
    #     raise InvalidAddressError(validator_address)

    validators_registry.delete_validator(validator_address)
    return validator_address


@check_forbidden_method_in_hosted_studio
def delete_all_validators(
    validators_registry: ValidatorsRegistry,
) -> list:
    validators_registry.delete_all_validators()
    return validators_registry.get_all_validators()


def get_all_validators(validators_registry: ValidatorsRegistry) -> list:
    return validators_registry.get_all_validators(include_private_key=False)


def get_validator(
    validators_registry: ValidatorsRegistry, validator_address: str
) -> dict:
    return validators_registry.get_validator(
        validator_address=validator_address, include_private_key=False
    )


def count_validators(validators_registry: ValidatorsRegistry) -> int:
    return validators_registry.count_validators()


####### GEN ENDPOINTS #######
async def get_contract_schema(
    accounts_manager: AccountsManager,
    msg_handler: MessageHandler,
    contract_address: str,
) -> dict:
    if not accounts_manager.is_valid_address(contract_address):
        raise InvalidAddressError(
            contract_address,
            "Incorrect address format. Please provide a valid address.",
        )
    contract_account = accounts_manager.get_account_or_fail(contract_address)

    if not contract_account["data"] or not contract_account["data"]["code"]:
        raise InvalidAddressError(
            contract_address,
            "Contract not deployed.",
        )

    node = Node(  # Mock node just to get the data from the GenVM
        contract_snapshot=None,
        validator_mode=ExecutionMode.LEADER,
        validator=Validator(
            address="",
            stake=0,
            llmprovider=LLMProvider(
                provider="",
                model="",
                config={},
                plugin="",
                plugin_config={},
            ),
        ),
        leader_receipt=None,
        msg_handler=msg_handler.with_client_session(get_client_session_id()),
        contract_snapshot_factory=None,
    )
    schema = await node.get_contract_schema(
        base64.b64decode(contract_account["data"]["code"])
    )
    return json.loads(schema)


async def get_contract_schema_for_code(
    msg_handler: MessageHandler, contract_code_hex: str
) -> dict:
    node = Node(  # Mock node just to get the data from the GenVM
        contract_snapshot=None,
        validator_mode=ExecutionMode.LEADER,
        validator=Validator(
            address="",
            stake=0,
            llmprovider=LLMProvider(
                provider="",
                model="",
                config={},
                plugin="",
                plugin_config={},
            ),
        ),
        leader_receipt=None,
        msg_handler=msg_handler.with_client_session(get_client_session_id()),
        contract_snapshot_factory=None,
    )
    schema = await node.get_contract_schema(
        eth_utils.hexadecimal.decode_hex(contract_code_hex)
    )
    return json.loads(schema)


async def gen_call(
    session: Session,
    accounts_manager: AccountsManager,
    msg_handler: MessageHandler,
    transactions_parser: TransactionParser,
    validators_registry: ValidatorsRegistry,
    params: dict,
) -> str:
    type = params["type"]
    data = params["data"]
    to_address = params["to"]
    from_address = params["from"] if "from" in params else None
    transaction_hash_variant = (
        params["transaction_hash_variant"]
        if "transaction_hash_variant" in params
        else None
    )

    if from_address is None:
        return base64.b64encode(b"\x00' * 31 + b'\x01").decode(
            "ascii"
        )  # Return '1' as a uint256

    if from_address and not accounts_manager.is_valid_address(from_address):
        raise InvalidAddressError(from_address)

    if not accounts_manager.is_valid_address(to_address):
        raise InvalidAddressError(to_address)

    if transaction_hash_variant == "latest-final":
        state_status = "finalized"
    else:
        state_status = "accepted"

    # Get a validator
    validators = get_all_validators(validators_registry)
    if validators:
        validator = validators[0]
    else:
        raise JSONRPCError(f"No validators exist to execute the gen_call")

    # Create validator node
    node = Node(
        contract_snapshot=ContractSnapshot(to_address, session),
        contract_snapshot_factory=partial(ContractSnapshot, session=session),
        validator_mode=ExecutionMode.LEADER,
        validator=Validator(
            id=validator["id"],
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
        leader_receipt=None,
        msg_handler=msg_handler.with_client_session(get_client_session_id()),
    )

    if type == "read":
        decoded_data = transactions_parser.decode_method_call_data(data)
        receipt = await node.get_contract_data(
            from_address="0x" + "00" * 20,
            calldata=decoded_data.calldata,
            state_status=state_status,
        )
    elif type == "write":
        decoded_data = transactions_parser.decode_method_send_data(data)
        receipt = await node.run_contract(
            from_address=from_address,
            calldata=decoded_data.calldata,
        )
    elif type == "deploy":
        decoded_data = transactions_parser.decode_deployment_data(data)
        receipt = await node.deploy_contract(
            from_address=from_address,
            code_to_deploy=decoded_data.contract_code,
            calldata=decoded_data.calldata,
        )
    else:
        raise JSONRPCError(f"Invalid type: {type}")

    # Return the result of the write method
    if receipt.execution_result != ExecutionResultStatus.SUCCESS:
        raise JSONRPCError(
            message="running contract failed", data={"receipt": receipt.to_dict()}
        )

    return eth_utils.hexadecimal.encode_hex(receipt.result[1:])[2:]


####### ETH ENDPOINTS #######
def get_balance(
    accounts_manager: AccountsManager, account_address: str, block_tag: str = "latest"
) -> int:
    if not accounts_manager.is_valid_address(account_address):
        raise InvalidAddressError(
            account_address, f"Invalid address from_address: {account_address}"
        )
    account_balance = accounts_manager.get_account_balance(account_address)
    return account_balance


def get_transaction_count(
    transactions_processor: TransactionsProcessor, address: str, block: str = "latest"
) -> int:
    return transactions_processor.get_transaction_count(address)


def vote_name_to_number(vote_name: str) -> int:
    if vote_name == Vote.AGREE.value:
        return 1
    elif vote_name == Vote.DISAGREE.value:
        return 2
    else:
        return 0


def votes_to_result(votes: list) -> str:
    if len(votes) == 0:
        return "5", "NO_MAJORITY"
    elif (
        len([vote for vote in votes if vote.lower() == Vote.AGREE.value])
        > len(votes) // 2
    ):
        return "6", "MAJORITY_AGREE"
    else:
        return "7", "MAJORITY_DISAGREE"


def get_validator_vote_hash(validator_address: str, vote_type: int, nonce: int) -> str:
    vote_hash = Web3.solidity_keccak(
        ["address", "uint8", "uint256"], [validator_address, vote_type, nonce]
    ).hex()
    return "0x" + vote_hash


def get_tx_execution_hash(leader_address: str, vote_type: int) -> str:
    tx_execution_hash = Web3.solidity_keccak(
        ["address", "uint8", "bytes32", "uint256"],
        [leader_address, vote_type, b"", 4444],
    ).hex()
    return "0x" + tx_execution_hash


def get_transaction_by_hash(
    transactions_processor: TransactionsProcessor, transaction_hash: str
) -> dict | None:
    transaction_data = transactions_processor.get_transaction_by_hash(transaction_hash)

    transaction_data["current_timestamp"] = str(round(time.time()))
    transaction_data["sender"] = transaction_data["from_address"]
    transaction_data["recipient"] = transaction_data["to_address"]
    transaction_data["num_of_initial_validators"] = str(
        transaction_data["num_of_initial_validators"]
    )
    transaction_data["tx_slot"] = "0"
    transaction_data["created_timestamp"] = str(
        int(datetime.fromisoformat(transaction_data["created_at"]).timestamp())
    )
    transaction_data["last_vote_timestamp"] = str(
        transaction_data["last_vote_timestamp"]
    )
    transaction_data["random_seed"] = "0x" + "0" * 64

    if (transaction_data["consensus_data"] is not None) and (
        "votes" in transaction_data["consensus_data"]
    ):
        votes_temp = transaction_data["consensus_data"]["votes"].values()
    else:
        votes_temp = []
    transaction_data["result"], transaction_data["result_name"] = votes_to_result(
        votes_temp
    )

    to_encode = []
    if transaction_data["data"] is not None:
        if "calldata" in transaction_data["data"]:
            encoded_call_data = base64.b64decode(transaction_data["data"]["calldata"])
            to_encode.append(encoded_call_data)
            to_encode.append(b"\x00")
        if "contract_code" in transaction_data["data"]:
            contract_code_bytes = base64.b64decode(
                transaction_data["data"]["contract_code"]
            )
            to_encode.insert(0, contract_code_bytes)
    if len(to_encode) == 0:
        transaction_data["tx_data"] = ""
    else:
        transaction_data["tx_data"] = Web3.to_hex(rlp.encode(to_encode))[2:]

    if (
        transaction_data["consensus_data"] is not None
        and "leader_receipt" in transaction_data["consensus_data"]
        and "node_config" in transaction_data["consensus_data"]["leader_receipt"]
    ):
        transaction_data["tx_execution_hash"] = get_tx_execution_hash(
            transaction_data["consensus_data"]["leader_receipt"]["node_config"][
                "address"
            ],
            vote_name_to_number(
                transaction_data["consensus_data"]["leader_receipt"]["vote"]
            ),
        )
    else:
        transaction_data["tx_execution_hash"] = ""

    kind = 0
    if (
        transaction_data["consensus_data"] is not None
        and "leader_receipt" in transaction_data["consensus_data"]
        and "result" in transaction_data["consensus_data"]["leader_receipt"]
    ):
        kind = base64.b64decode(
            transaction_data["consensus_data"]["leader_receipt"]["result"]
        )[0]

    eq_output = []
    if (
        "consensus_history" in transaction_data
        and "consensus_results" in transaction_data["consensus_history"]
    ):
        for consensus_round in transaction_data["consensus_history"][
            "consensus_results"
        ]:
            if consensus_round["leader_result"] is not None:
                eq_output.append(
                    [
                        len(eq_output),  # key
                        [
                            base64.b64decode(
                                consensus_round["leader_result"]["result"]
                            )[
                                0
                            ],  # kind
                            "\x00",
                        ],
                    ]
                )  # data
    pending_transactions = []
    messages = []
    if (
        transaction_data["consensus_data"] is not None
        and "leader_receipt" in transaction_data["consensus_data"]
        and transaction_data["consensus_data"]["leader_receipt"] is not None
        and "pending_transactions"
        in transaction_data["consensus_data"]["leader_receipt"]
        and transaction_data["consensus_data"]["leader_receipt"]["pending_transactions"]
        is not None
    ):
        for message in transaction_data["consensus_data"]["leader_receipt"][
            "pending_transactions"
        ]:
            pending_transactions.append(
                [
                    message["address"] if "address" in message else "",  # Account
                    message["calldata"] if "calldata" in message else "",  # Calldata
                    message["value"] if "value" in message else 0,  # Value
                    message["on"] if "on" in message else "finalized",  # On
                    message["code"] if "code" in message else "",  # Code
                    (
                        message["salt_nonce"] if "salt_nonce" in message else 0
                    ),  # SaltNonce
                ]
            )
            messages.append(
                {
                    "messageType": "0",
                    "recipient": message["address"] if "address" in message else "",
                    "value": message["value"] if "value" in message else 0,
                    "data": message["calldata"] if "calldata" in message else "",
                    "onAcceptance": (
                        message["on"] == "accepted" if "on" in message else False
                    ),
                }
            )
    transaction_data["eq_blocks_outputs"] = Web3.to_hex(
        rlp.encode(
            [
                [
                    [kind, "\x00"],  # data
                    pending_transactions,
                    [],  # pending eth transactions
                    bytes.fromhex(""),
                ],  # storage proof
                eq_output,
            ]
        )
    )
    transaction_data["messages"] = messages

    if transaction_data["status"] in [
        TransactionStatus.PENDING.value,
        TransactionStatus.ACTIVATED.value,
    ]:
        transaction_data["queue_type"] = "1"
    elif transaction_data["status"] == TransactionStatus.ACCEPTED.value:
        transaction_data["queue_type"] = "2"
    elif transaction_data["status"] == TransactionStatus.UNDETERMINED.value:
        transaction_data["queue_type"] = "3"
    else:
        transaction_data["queue_type"] = "0"

    transaction_data["queue_position"] = "0"

    if "consensus_results" in transaction_data["consensus_history"]:
        transaction_data["activator"] = transaction_data["consensus_history"][
            "consensus_results"
        ][0]["leader_result"]["node_config"]["address"]
    else:
        transaction_data["activator"] = ""

    if (transaction_data["consensus_data"] is not None) and (
        "leader_receipt" in transaction_data["consensus_data"]
    ):
        transaction_data["last_leader"] = transaction_data["consensus_data"][
            "leader_receipt"
        ]["node_config"]["address"]
    else:
        transaction_data["last_leader"] = ""

    transaction_data["status"] = transaction_data["status"]
    transaction_data["tx_id"] = transaction_data["hash"]
    transaction_data["read_state_block_range"] = {
        "activation_block": "0",
        "processing_block": "0",
        "proposal_block": "0",
    }

    if "consensus_results" in transaction_data["consensus_history"]:
        transaction_data["num_of_rounds"] = str(
            len(transaction_data["consensus_history"]["consensus_results"])
        )
    else:
        transaction_data["num_of_rounds"] = "0"

    validator_votes_name = []
    validator_votes = []
    validator_votes_hash = []
    round_validators = []
    if "consensus_results" in transaction_data["consensus_history"]:
        round_number = str(
            len(transaction_data["consensus_history"]["consensus_results"]) - 1
        )
        last_round = transaction_data["consensus_history"]["consensus_results"][-1]
        if "leader_result" in last_round:
            leader = last_round["leader_result"]
            if leader is not None:
                validator_votes_name.append(leader["vote"].upper())
                vote_number = vote_name_to_number(leader["vote"])
                validator_votes.append(vote_number)
                leader_address = leader["node_config"]["address"]
                validator_votes_hash.append(
                    get_validator_vote_hash(
                        leader_address, vote_number, transaction_data["nonce"]
                    )
                )
                round_validators.append(leader_address)

        for validator in last_round["validator_results"]:
            validator_votes_name.append(validator["vote"].upper())
            vote_number = vote_name_to_number(validator["vote"])
            validator_votes.append(vote_number)
            validator_address = validator["node_config"]["address"]
            validator_votes_hash.append(
                get_validator_vote_hash(
                    validator_address, vote_number, transaction_data["nonce"]
                )
            )
            round_validators.append(validator_address)
    else:
        round_number = "0"
    last_round_result, _ = votes_to_result(validator_votes_name)

    transaction_data["last_round"] = {
        "round": round_number,
        "leader_index": "0",
        "votes_committed": str(len(validator_votes_name)),
        "votes_revealed": str(len(validator_votes_name)),
        "appeal_bond": "0",
        "rotations_left": str(
            transaction_data["config_rotation_rounds"]
            - transaction_data["rotation_count"]
        ),
        "result": last_round_result,
        "round_validators": round_validators,
        "validator_votes_hash": validator_votes_hash,
        "validator_votes": validator_votes,
        "validator_votes_name": validator_votes_name,
    }
    return transaction_data


async def eth_call(
    session: Session,
    accounts_manager: AccountsManager,
    msg_handler: MessageHandler,
    transactions_parser: TransactionParser,
    params: dict,
    block_tag: str = "latest",
) -> str:
    to_address = params["to"]
    from_address = params["from"] if "from" in params else None
    data = params["data"]

    if from_address is None:
        return base64.b64encode(b"\x00' * 31 + b'\x01").decode(
            "ascii"
        )  # Return '1' as a uint256

    if from_address and not accounts_manager.is_valid_address(from_address):
        raise InvalidAddressError(from_address)

    if not accounts_manager.is_valid_address(to_address):
        raise InvalidAddressError(to_address)

    decoded_data = transactions_parser.decode_method_call_data(data)

    node = Node(  # Mock node just to get the data from the GenVM
        contract_snapshot=ContractSnapshot(to_address, session),
        contract_snapshot_factory=partial(ContractSnapshot, session=session),
        validator_mode=ExecutionMode.LEADER,
        validator=Validator(
            address="",
            stake=0,
            llmprovider=LLMProvider(
                provider="",
                model="",
                config={},
                plugin="",
                plugin_config={},
            ),
        ),
        leader_receipt=None,
        msg_handler=msg_handler.with_client_session(get_client_session_id()),
    )

    receipt = await node.get_contract_data(
        from_address="0x" + "00" * 20,
        calldata=decoded_data.calldata,
    )
    if receipt.execution_result != ExecutionResultStatus.SUCCESS:
        raise JSONRPCError(
            message="running contract failed", data={"receipt": receipt.to_dict()}
        )
    return eth_utils.hexadecimal.encode_hex(receipt.result[1:])


def send_raw_transaction(
    transactions_processor: TransactionsProcessor,
    msg_handler: MessageHandler,
    accounts_manager: AccountsManager,
    transactions_parser: TransactionParser,
    consensus_service: ConsensusService,
    signed_rollup_transaction: str,
) -> str:
    # Decode transaction
    decoded_rollup_transaction = transactions_parser.decode_signed_transaction(
        signed_rollup_transaction
    )
    print("DECODED ROLLUP TRANSACTION", decoded_rollup_transaction)

    # Validate transaction
    if decoded_rollup_transaction is None:
        raise InvalidTransactionError("Invalid transaction data")

    from_address = decoded_rollup_transaction.from_address
    value = decoded_rollup_transaction.value

    if not accounts_manager.is_valid_address(from_address):
        raise InvalidAddressError(
            from_address, f"Invalid address from_address: {from_address}"
        )

    transaction_signature_valid = transactions_parser.transaction_has_valid_signature(
        signed_rollup_transaction, decoded_rollup_transaction
    )
    if not transaction_signature_valid:
        raise InvalidTransactionError("Transaction signature verification failed")

    if isinstance(decoded_rollup_transaction.data, DecodedsubmitAppealDataArgs):
        tx_id = decoded_rollup_transaction.data.tx_id
        tx_id_hex = "0x" + tx_id.hex() if isinstance(tx_id, bytes) else tx_id
        transactions_processor.set_transaction_appeal(tx_id_hex, True)
        msg_handler.send_message(
            log_event=LogEvent(
                "transaction_appeal_updated",
                EventType.INFO,
                EventScope.CONSENSUS,
                "Set transaction appealed",
                {
                    "hash": tx_id_hex,
                },
            ),
            log_to_terminal=False,
        )
        return tx_id_hex
    else:
        rollup_transaction_details = consensus_service.add_transaction(
            signed_rollup_transaction, from_address
        )

        to_address = decoded_rollup_transaction.to_address
        nonce = decoded_rollup_transaction.nonce
        value = decoded_rollup_transaction.value
        genlayer_transaction = transactions_parser.get_genlayer_transaction(
            decoded_rollup_transaction
        )

        transaction_data = {}
        leader_only = False
        if genlayer_transaction.type != TransactionType.SEND:
            leader_only = genlayer_transaction.data.leader_only

        if genlayer_transaction.type == TransactionType.DEPLOY_CONTRACT:
            if value > 0:
                raise InvalidTransactionError("Deploy Transaction can't send value")

            if (
                rollup_transaction_details is None
                or not "recipient" in rollup_transaction_details
            ):
                new_account = accounts_manager.create_new_account()
                new_contract_address = new_account.address
            else:
                new_contract_address = rollup_transaction_details["recipient"]
                accounts_manager.create_new_account_with_address(new_contract_address)

            transaction_data = {
                "contract_address": new_contract_address,
                "contract_code": genlayer_transaction.data.contract_code,
                "calldata": genlayer_transaction.data.calldata,
            }
            to_address = new_contract_address
        elif genlayer_transaction.type == TransactionType.RUN_CONTRACT:
            # Contract Call
            if not accounts_manager.is_valid_address(to_address):
                raise InvalidAddressError(
                    to_address, f"Invalid address to_address: {to_address}"
                )

            to_address = genlayer_transaction.to_address
            transaction_data = {"calldata": genlayer_transaction.data.calldata}

        # Obtain transaction hash from new transaction event
        if rollup_transaction_details and "tx_id_hex" in rollup_transaction_details:
            transaction_hash = rollup_transaction_details["tx_id_hex"]
        else:
            transaction_hash = None

        # Insert transaction into the database
        transaction_hash = transactions_processor.insert_transaction(
            genlayer_transaction.from_address,
            to_address,
            transaction_data,
            value,
            genlayer_transaction.type.value,
            nonce,
            leader_only,
            genlayer_transaction.max_rotations,
            None,
            transaction_hash,
            genlayer_transaction.num_of_initial_validators,
        )

        return transaction_hash


def get_transactions_for_address(
    transactions_processor: TransactionsProcessor,
    accounts_manager: AccountsManager,
    address: str,
    filter: str = TransactionAddressFilter.ALL.value,
) -> list[dict]:
    if not accounts_manager.is_valid_address(address):
        raise InvalidAddressError(address)

    return transactions_processor.get_transactions_for_address(
        address, TransactionAddressFilter(filter)
    )


@check_forbidden_method_in_hosted_studio
def set_finality_window_time(consensus: ConsensusAlgorithm, time: int) -> None:
    consensus.set_finality_window_time(time)


def get_finality_window_time(consensus: ConsensusAlgorithm) -> int:
    return consensus.finality_window_time


def get_chain_id() -> str:
    return hex(SIMULATOR_CHAIN_ID)


def get_net_version() -> str:
    return str(SIMULATOR_CHAIN_ID)


def get_block_number(transactions_processor: TransactionsProcessor) -> str:
    transaction_count = transactions_processor.get_highest_timestamp()
    return hex(transaction_count)


def get_block_by_number(
    transactions_processor: TransactionsProcessor, block_number: str, full_tx: bool
) -> dict:
    block_number_int = 0

    if block_number == "latest":
        # Get latest block number using existing method
        block_number_int = int(get_block_number(transactions_processor), 16)
    else:
        try:
            block_number_int = int(block_number, 16)
        except ValueError:
            raise JSONRPCError(f"Invalid block number format: {block_number}")

    block_details = transactions_processor.get_transactions_for_block(
        block_number_int, include_full_tx=full_tx
    )

    if not block_details:
        raise JSONRPCError(f"Block not found for number: {block_number}")

    return block_details


def get_gas_price() -> str:
    gas_price_in_wei = 0
    return hex(gas_price_in_wei)


def get_gas_estimate(data: Any) -> str:
    gas_price_in_wei = 30 * 10**6
    return hex(gas_price_in_wei)


def get_transaction_receipt(
    transactions_processor: TransactionsProcessor,
    transaction_hash: str,
) -> dict | None:

    transaction = transactions_processor.get_transaction_by_hash(transaction_hash)

    event_signature = "NewTransaction(bytes32,address,address)"
    event_signature_hash = eth_utils.keccak(text=event_signature).hex()

    logs = [
        {
            "address": transaction.get("to_address"),
            "topics": [
                f"0x{event_signature_hash}",
                transaction_hash,
                "0x000000000000000000000000"
                + transaction.get("to_address").replace("0x", ""),
                "0x000000000000000000000000"
                + transaction.get("from_address").replace("0x", ""),
            ],
            "data": "0x",
            "blockNumber": 0,
            "transactionHash": transaction_hash,
            "transactionIndex": 0,
            "blockHash": transaction_hash,
            "logIndex": 0,
            "removed": False,
        }
    ]

    receipt = {
        "transactionHash": transaction_hash,
        "transactionIndex": hex(0),
        "blockHash": transaction_hash,
        "blockNumber": hex(transaction.get("block_number", 0)),
        "from": transaction.get("from_address"),
        "to": transaction.get("to_address") if transaction.get("to_address") else None,
        "cumulativeGasUsed": hex(transaction.get("gas_used", 21000)),
        "gasUsed": hex(transaction.get("gas_used", 21000)),
        "contractAddress": (
            transaction.get("contract_address")
            if transaction.get("contract_address")
            else None
        ),
        "logs": logs,
        "logsBloom": "0x" + "00" * 256,
        "status": hex(1 if transaction.get("status", True) else 0),
    }

    return receipt


def get_block_by_hash(
    transactions_processor: TransactionsProcessor,
    transaction_hash: str,
    full_tx: bool = False,
) -> dict | None:

    transaction = transactions_processor.get_transaction_by_hash(transaction_hash)

    if not transaction:
        return None

    block_details = {
        "hash": transaction_hash,
        "parentHash": "0x" + "00" * 32,
        "number": hex(transaction.get("block_number", 0)),
        "timestamp": hex(transaction.get("timestamp", 0)),
        "nonce": "0x" + "00" * 8,
        "transactionsRoot": "0x" + "00" * 32,
        "stateRoot": "0x" + "00" * 32,
        "receiptsRoot": "0x" + "00" * 32,
        "miner": "0x" + "00" * 20,
        "difficulty": "0x1",
        "totalDifficulty": "0x1",
        "size": "0x0",
        "extraData": "0x",
        "gasLimit": hex(transaction.get("gas_limit", 8000000)),
        "gasUsed": hex(transaction.get("gas_used", 21000)),
        "logsBloom": "0x" + "00" * 256,
        "transactions": [],
    }

    if full_tx:
        block_details["transactions"].append(transaction)
    else:
        block_details["transactions"].append(transaction_hash)

    return block_details


def get_contract(consensus_service: ConsensusService, contract_name: str) -> dict:
    """
    Get contract instance by name

    Args:
        consensus_service: The consensus service instance
        contract_name: Name of the contract to retrieve

    Returns:
        dict: Contract information including address and ABI
    """
    contract = consensus_service.load_contract(contract_name)

    if contract is None:
        raise JSONRPCError(
            message=f"Contract {contract_name} not found",
            data={"contract_name": contract_name},
        )

    return {
        "address": contract["address"],
        "abi": contract["abi"],
        "bytecode": contract["bytecode"],
    }


@check_forbidden_method_in_hosted_studio
def create_snapshot(
    snapshot_manager: SnapshotManager,
) -> int:
    """Create a new snapshot of the current state and transactions.

    Returns:
        int: The snapshot ID
    """
    snapshot = snapshot_manager.create_snapshot()
    return snapshot.snapshot_id


@check_forbidden_method_in_hosted_studio
def restore_snapshot(
    snapshot_manager: SnapshotManager,
    snapshot_id: int,
) -> bool:
    """Restore the database state from a snapshot.

    Args:
        snapshot_id: ID of the snapshot to restore

    Returns:
        bool: True if the snapshot was restored, False otherwise
    """
    reverted = snapshot_manager.restore_snapshot(snapshot_id)
    return reverted


@check_forbidden_method_in_hosted_studio
def delete_all_snapshots(
    snapshot_manager: SnapshotManager,
) -> dict:
    """Delete all snapshots from the database.

    Returns:
        dict: Information about the deletion result
    """
    deleted_count = snapshot_manager.delete_all_snapshots()
    return {"deleted_count": deleted_count}


def register_all_rpc_endpoints(
    jsonrpc: JSONRPC,
    msg_handler: MessageHandler,
    request_session: Session,
    accounts_manager: AccountsManager,
    snapshot_manager: SnapshotManager,
    transactions_processor: TransactionsProcessor,
    validators_registry: ValidatorsRegistry,
    llm_provider_registry: LLMProviderRegistry,
    consensus: ConsensusAlgorithm,
    consensus_service: ConsensusService,
    transactions_parser: TransactionParser,
):
    register_rpc_endpoint = partial(generate_rpc_endpoint, jsonrpc, msg_handler)

    register_rpc_endpoint(ping)
    register_rpc_endpoint(
        partial(clear_db_tables, request_session),
        method_name="sim_clearDbTables",
    )
    register_rpc_endpoint(
        partial(fund_account, accounts_manager, transactions_processor),
        method_name="sim_fundAccount",
    )
    register_rpc_endpoint(
        partial(get_providers_and_models, llm_provider_registry),
        method_name="sim_getProvidersAndModels",
    )
    register_rpc_endpoint(
        partial(reset_defaults_llm_providers, llm_provider_registry),
        method_name="sim_resetDefaultsLlmProviders",
    )
    register_rpc_endpoint(
        partial(add_provider, llm_provider_registry),
        method_name="sim_addProvider",
    )
    register_rpc_endpoint(
        partial(update_provider, llm_provider_registry),
        method_name="sim_updateProvider",
    )
    register_rpc_endpoint(
        partial(delete_provider, llm_provider_registry),
        method_name="sim_deleteProvider",
    )
    register_rpc_endpoint(
        partial(
            check_forbidden_method_in_hosted_studio(create_validator),
            validators_registry,
            accounts_manager,
        ),
        method_name="sim_createValidator",
    )
    register_rpc_endpoint(
        partial(
            create_random_validator,
            validators_registry,
            accounts_manager,
            llm_provider_registry,
        ),
        method_name="sim_createRandomValidator",
    )
    register_rpc_endpoint(
        partial(
            create_random_validators,
            validators_registry,
            accounts_manager,
            llm_provider_registry,
        ),
        method_name="sim_createRandomValidators",
    )
    register_rpc_endpoint(
        partial(update_validator, validators_registry, accounts_manager),
        method_name="sim_updateValidator",
    )
    register_rpc_endpoint(
        partial(delete_validator, validators_registry, accounts_manager),
        method_name="sim_deleteValidator",
    )
    register_rpc_endpoint(
        partial(delete_all_validators, validators_registry),
        method_name="sim_deleteAllValidators",
    )
    register_rpc_endpoint(
        partial(get_all_validators, validators_registry),
        method_name="sim_getAllValidators",
    )
    register_rpc_endpoint(
        partial(get_validator, validators_registry),
        method_name="sim_getValidator",
    )
    register_rpc_endpoint(
        partial(count_validators, validators_registry),
        method_name="sim_countValidators",
    )
    register_rpc_endpoint(
        partial(get_contract_schema, accounts_manager, msg_handler),
        method_name="gen_getContractSchema",
    )
    register_rpc_endpoint(
        partial(get_contract_schema_for_code, msg_handler),
        method_name="gen_getContractSchemaForCode",
    )
    register_rpc_endpoint(
        partial(
            gen_call,
            request_session,
            accounts_manager,
            msg_handler,
            transactions_parser,
            validators_registry,
        ),
        method_name="gen_call",
    )
    register_rpc_endpoint(
        partial(get_balance, accounts_manager),
        method_name="eth_getBalance",
    )
    register_rpc_endpoint(
        partial(get_transaction_by_hash, transactions_processor),
        method_name="eth_getTransactionByHash",
    )
    register_rpc_endpoint(
        partial(
            eth_call,
            request_session,
            accounts_manager,
            msg_handler,
            transactions_parser,
        ),
        method_name="eth_call",
    )
    register_rpc_endpoint(
        partial(
            send_raw_transaction,
            transactions_processor,
            msg_handler,
            accounts_manager,
            transactions_parser,
            consensus_service,
        ),
        method_name="eth_sendRawTransaction",
    )
    register_rpc_endpoint(
        partial(get_transaction_count, transactions_processor),
        method_name="eth_getTransactionCount",
    )
    register_rpc_endpoint(
        partial(get_transactions_for_address, transactions_processor, accounts_manager),
        method_name="sim_getTransactionsForAddress",
    )
    register_rpc_endpoint(
        partial(set_finality_window_time, consensus),
        method_name="sim_setFinalityWindowTime",
    )
    register_rpc_endpoint(
        partial(get_finality_window_time, consensus),
        method_name="sim_getFinalityWindowTime",
    )
    register_rpc_endpoint(
        partial(get_contract, consensus_service),
        method_name="sim_getConsensusContract",
    )
    register_rpc_endpoint(get_chain_id, method_name="eth_chainId")
    register_rpc_endpoint(get_net_version, method_name="net_version")
    register_rpc_endpoint(
        partial(get_block_number, transactions_processor),
        method_name="eth_blockNumber",
    )
    register_rpc_endpoint(
        partial(get_block_by_number, transactions_processor),
        method_name="eth_getBlockByNumber",
    )
    register_rpc_endpoint(get_gas_price, method_name="eth_gasPrice")
    register_rpc_endpoint(get_gas_estimate, method_name="eth_estimateGas")
    register_rpc_endpoint(
        partial(get_transaction_receipt, transactions_processor),
        method_name="eth_getTransactionReceipt",
    )
    register_rpc_endpoint(
        partial(get_block_by_hash, transactions_processor),
        method_name="eth_getBlockByHash",
    )
    register_rpc_endpoint(
        partial(create_snapshot, snapshot_manager),
        method_name="sim_createSnapshot",
    )
    register_rpc_endpoint(
        partial(restore_snapshot, snapshot_manager),
        method_name="sim_restoreSnapshot",
    )
    register_rpc_endpoint(
        partial(delete_all_snapshots, snapshot_manager),
        method_name="sim_deleteAllSnapshots",
    )
