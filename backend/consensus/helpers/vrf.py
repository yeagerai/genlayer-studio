from datetime import datetime
import numpy as np


def get_validators_for_transaction(
    nodes: list[dict],
    num_validators: int,
    rng=np.random.default_rng(seed=int(datetime.now().timestamp())),
) -> list[dict]:
    """
    Returns subset of validators for a transaction.
    The selelction and order is given by a random sampling based on the stake of the validators.
    """
    num_validators = min(num_validators, len(nodes))

    total_stake = sum(validator["stake"] for validator in nodes)
    probabilities = [validator["stake"] / total_stake for validator in nodes]

    selected_validators = rng.choice(
        nodes,
        p=probabilities,
        size=num_validators,
        replace=False,
    )

    return list(selected_validators)
