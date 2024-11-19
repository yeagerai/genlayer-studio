from dataclasses import dataclass
from backend.node.genvm.types import Receipt


@dataclass
class ConsensusData:
    votes: dict[str, str]
    leader_receipt: Receipt | None
    validators: list[Receipt] | None = None

    def to_dict(self):
        return {
            "votes": self.votes,
            "leader_receipt": (
                self.leader_receipt.to_dict() if self.leader_receipt else None
            ),
            "validators": [receipt.to_dict() for receipt in self.validators],
        }
