# rpc/endpoints.py
import random
import json
from functools import partial
from typing import Any
from flask_jsonrpc import JSONRPC
from flask_jsonrpc.exceptions import JSONRPCError
from sqlalchemy import Table
from sqlalchemy.orm import Session

import backend.node.genvm.origin.calldata as genvm_calldata

from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.llm_providers import LLMProviderRegistry
from backend.database_handler.models import Base
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
from backend.protocol_rpc.transactions_parser import (
    decode_signed_transaction,
    transaction_has_valid_signature,
    decode_method_call_data,
    decode_deployment_data,
)
from backend.errors.errors import InvalidAddressError, InvalidTransactionError

from backend.database_handler.transactions_processor import (
    TransactionAddressFilter,
    TransactionsProcessor,
)
from backend.node.base import Node
from backend.node.types import ExecutionMode, ExecutionResultStatus

from flask import request
from flask_jsonrpc.exceptions import JSONRPCError
import base64


####### HELPER ENDPOINTS #######
def ping() -> str:
    return "OK"


####### SIMULATOR ENDPOINTS #######
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
        None, account_address, None, amount, 0, nonce, False
    )
    return transaction_hash


def reset_defaults_llm_providers(llm_provider_registry: LLMProviderRegistry) -> None:
    llm_provider_registry.reset_defaults()


async def get_providers_and_models(
    llm_provider_registry: LLMProviderRegistry,
) -> list[dict]:
    return await llm_provider_registry.get_all_dict()


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

    new_address = accounts_manager.create_new_account().address
    return validators_registry.create_validator(
        Validator(
            address=new_address,
            stake=stake,
            llmprovider=llm_provider,
        )
    )


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
        validator_address = accounts_manager.create_new_account().address

        validator = validators_registry.create_validator(
            Validator(address=validator_address, stake=stake, llmprovider=detail)
        )
        response.append(validator)

    return response


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


def delete_all_validators(
    validators_registry: ValidatorsRegistry,
) -> list:
    validators_registry.delete_all_validators()
    return validators_registry.get_all_validators()


def get_all_validators(validators_registry: ValidatorsRegistry) -> list:
    return validators_registry.get_all_validators()


def get_validator(
    validators_registry: ValidatorsRegistry, validator_address: str
) -> dict:
    return validators_registry.get_validator(validator_address)


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
    schema = await node.get_contract_schema(contract_account["data"]["code"])
    return json.loads(schema)


async def get_contract_schema_for_code(
    msg_handler: MessageHandler, contract_code: str
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
    schema = await node.get_contract_schema(contract_code)
    return json.loads(schema)


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
    transactions_processor: TransactionsProcessor, address: str
) -> int:
    return transactions_processor.get_transaction_count(address)


def get_transaction_by_hash(
    transactions_processor: TransactionsProcessor, transaction_hash: str
) -> dict | None:
    return transactions_processor.get_transaction_by_hash(transaction_hash)


async def call(
    session: Session,
    accounts_manager: AccountsManager,
    msg_handler: MessageHandler,
    params: dict,
    block_tag: str = "latest",
) -> str:
    to_address = params["to"]
    from_address = params["from"] if "from" in params else None
    data = params["data"]

    if from_address and not accounts_manager.is_valid_address(from_address):
        raise InvalidAddressError(from_address)

    if not accounts_manager.is_valid_address(to_address):
        raise InvalidAddressError(to_address)

    decoded_data = decode_method_call_data(data)

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
    return base64.b64encode(receipt.result[1:]).decode("ascii")


def send_raw_transaction(
    transactions_processor: TransactionsProcessor,
    accounts_manager: AccountsManager,
    signed_transaction: str,
) -> str:
    # Decode transaction
    decoded_transaction = decode_signed_transaction(signed_transaction)
    print("decoded_transaction", decoded_transaction)

    # Validate transaction
    if decoded_transaction is None:
        raise InvalidTransactionError("Invalid transaction data")

    from_address = decoded_transaction.from_address
    value = decoded_transaction.value

    if not accounts_manager.is_valid_address(from_address):
        raise InvalidAddressError(
            from_address, f"Invalid address from_address: {from_address}"
        )

    transaction_signature_valid = transaction_has_valid_signature(
        signed_transaction, decoded_transaction
    )
    if not transaction_signature_valid:
        raise InvalidTransactionError("Transaction signature verification failed")

    to_address = decoded_transaction.to_address
    nonce = decoded_transaction.nonce

    transaction_data = {}
    result = {}
    transaction_type: TransactionType
    leader_only = False
    if not decoded_transaction.data:
        # Sending value transaction
        transaction_type = TransactionType.SEND
    elif not to_address or to_address == "0x":
        # Contract deployment
        if value > 0:
            raise InvalidTransactionError("Deploy Transaction can't send value")

        decoded_data = decode_deployment_data(decoded_transaction.data)
        new_contract_address = accounts_manager.create_new_account().address

        transaction_data = {
            "contract_address": new_contract_address,
            "contract_code": decoded_data.contract_code,
            "calldata": decoded_data.calldata,
        }
        result["contract_address"] = new_contract_address
        to_address = new_contract_address
        transaction_type = TransactionType.DEPLOY_CONTRACT
        leader_only = decoded_data.leader_only
    else:
        # Contract Call
        if not accounts_manager.is_valid_address(to_address):
            raise InvalidAddressError(
                to_address, f"Invalid address to_address: {to_address}"
            )
        decoded_data = decode_method_call_data(decoded_transaction.data)
        transaction_data = {"calldata": decoded_data.calldata}
        transaction_type = TransactionType.RUN_CONTRACT
        leader_only = decoded_data.leader_only

    # Insert transaction into the database
    transaction_hash = transactions_processor.insert_transaction(
        from_address,
        to_address,
        transaction_data,
        value,
        transaction_type.value,
        nonce,
        leader_only,
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


def register_all_rpc_endpoints(
    jsonrpc: JSONRPC,
    msg_handler: MessageHandler,
    request_session: Session,
    accounts_manager: AccountsManager,
    transactions_processor: TransactionsProcessor,
    validators_registry: ValidatorsRegistry,
    llm_provider_registry: LLMProviderRegistry,
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
        partial(create_validator, validators_registry, accounts_manager),
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
        partial(get_balance, accounts_manager),
        method_name="eth_getBalance",
    )
    register_rpc_endpoint(
        partial(get_transaction_by_hash, transactions_processor),
        method_name="eth_getTransactionByHash",
    )
    register_rpc_endpoint(
        partial(call, request_session, accounts_manager, msg_handler),
        method_name="eth_call",
    )
    register_rpc_endpoint(
        partial(send_raw_transaction, transactions_processor, accounts_manager),
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
