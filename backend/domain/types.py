# Types from our domain
# Trying to follow [hexagonal architecture](https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)) or layered architecture.
# These types should not depend on any other layer.

from dataclasses import dataclass
import decimal
from enum import Enum, IntEnum

from backend.database_handler.models import TransactionStatus
from backend.database_handler.types import ConsensusData


@dataclass()
class LLMProvider:
    provider: str
    model: str
    config: dict
    plugin: str
    plugin_config: dict
    id: int | None = None

    def __hash__(self):
        return hash(
            (
                self.id,
                self.provider,
                self.model,
                frozenset(self.config.items()),
                frozenset(self.plugin_config.items()),
            )
        )


@dataclass()
class Validator:
    address: str
    stake: int
    llmprovider: LLMProvider
    id: int | None = None

    def to_dict(self):
        result = {
            "address": self.address,
            "stake": self.stake,
            "provider": self.llmprovider.provider,
            "model": self.llmprovider.model,
            "config": self.llmprovider.config,
            "plugin": self.llmprovider.plugin,
            "plugin_config": self.llmprovider.plugin_config,
        }

        if self.id:
            result["id"] = self.id

        return result


class TransactionType(IntEnum):
    SEND = 0
    DEPLOY_CONTRACT = 1
    RUN_CONTRACT = 2


@dataclass
class Transaction:
    hash: str
    status: TransactionStatus
    type: TransactionType
    from_address: str | None
    to_address: str | None
    input_data: dict | None = None
    data: dict | None = None
    consensus_data: ConsensusData | None = None
    nonce: int | None = None
    value: int | None = None
    gaslimit: int | None = None
    r: int | None = None
    s: int | None = None
    v: int | None = None
    leader_only: bool = (
        False  # Flag to indicate if this transaction should be processed only by the leader. Used for fast and cheap execution of transactions.
    )
    created_at: str | None = None
    ghost_contract_address: str | None = None
    appealed: bool = False
    timestamp_awaiting_finalization: int | None = None
    appeal_failed: int = 0
    appeal_undetermined: bool = False

    def to_dict(self):
        return {
            "hash": self.hash,
            "status": self.status.value,
            "type": self.type.value,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "input_data": self.input_data,
            "data": self.data,
            "consensus_data": self.consensus_data,
            "nonce": self.nonce,
            "value": self.value,
            "gaslimit": self.gaslimit,
            "r": self.r,
            "s": self.s,
            "v": self.v,
            "leader_only": self.leader_only,
            "created_at": self.created_at,
            "ghost_contract_address": self.ghost_contract_address,
            "appealed": self.appealed,
            "timestamp_awaiting_finalization": self.timestamp_awaiting_finalization,
            "appeal_failed": self.appeal_failed,
            "appeal_undetermined": self.appeal_undetermined,
        }

    @classmethod
    def from_dict(cls, input: dict) -> "Transaction":
        return cls(
            hash=input["hash"],
            status=TransactionStatus(input["status"]),
            type=TransactionType(input["type"]),
            from_address=input.get("from_address"),
            to_address=input.get("to_address"),
            input_data=input.get("input_data"),
            data=input.get("data"),
            consensus_data=ConsensusData.from_dict(input.get("consensus_data")),
            nonce=input.get("nonce"),
            value=input.get("value"),
            gaslimit=input.get("gaslimit"),
            r=input.get("r"),
            s=input.get("s"),
            v=input.get("v"),
            leader_only=input.get("leader_only", False),
            created_at=input.get("created_at"),
            ghost_contract_address=input.get("ghost_contract_address"),
            appealed=input.get("appealed"),
            timestamp_awaiting_finalization=input.get(
                "timestamp_awaiting_finalization"
            ),
            appeal_failed=input.get("appeal_failed", 0),
            appeal_undetermined=input.get("appeal_undetermined", False),
        )
