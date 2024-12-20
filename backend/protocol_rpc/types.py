from enum import Enum
from dataclasses import dataclass, field


class EndpointResultStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"


@dataclass
class EndpointResult:
    status: EndpointResultStatus
    message: str
    data: dict = field(default_factory=dict)
    exception: Exception = None

    def to_json(self) -> dict[str]:
        return {
            "status": self.status.value,
            "message": self.message,
            "data": self.data,
            "exception": str(self.exception) if self.exception else None,
        }


@dataclass
class DecodedTransaction:
    from_address: str
    to_address: str
    data: str  # hex encoded
    type: str
    nonce: int
    value: int


@dataclass
class DecodedMethodCallData:
    calldata: bytes
    leader_only: bool = False


@dataclass
class DecodedDeploymentData:
    contract_code: bytes
    calldata: bytes
    leader_only: bool = False
