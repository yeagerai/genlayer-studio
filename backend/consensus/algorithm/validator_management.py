from typing import List, Tuple, Dict
from backend.database_handler.types import ConsensusData
from backend.node.types import Receipt
from backend.consensus.helpers.vrf import get_validators_for_transaction


class ValidatorManagement:
    @staticmethod
    def get_validators_from_consensus_data(
        all_validators: List[dict],
        consensus_data: ConsensusData,
        include_leader: bool,
    ) -> Tuple[List[dict], Dict[str, dict]]:
        """
        Get validators from consensus data.

        Args:
            all_validators (List[dict]): List of all validators.
            consensus_data (ConsensusData): Data related to the consensus process.
            include_leader (bool): Whether to get the leader in the validator set.

        Returns:
            Tuple[List[dict], Dict[str, dict]]: A tuple containing:
                - List of validators involved in the consensus process
                - Dictionary mapping addresses to validators not used in the consensus process
        """
        validator_map = {
            validator["address"]: validator for validator in all_validators
        }

        if include_leader:
            receipt_addresses = [consensus_data.leader_receipt.node_config["address"]]
        else:
            receipt_addresses = []

        receipt_addresses += [
            receipt.node_config["address"] for receipt in consensus_data.validators
        ]

        validators = [
            validator_map.pop(receipt_address)
            for receipt_address in receipt_addresses
            if receipt_address in validator_map
        ]

        return validators, validator_map

    @staticmethod
    def get_used_leader_addresses_from_consensus_history(
        consensus_history: dict,
        current_leader_receipt: Receipt | None = None,
    ) -> set[str]:
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
                    used_leader_addresses.update(
                        [leader_receipt["node_config"]["address"]]
                    )

        if current_leader_receipt:
            used_leader_addresses.update(
                [current_leader_receipt.node_config["address"]]
            )

        return used_leader_addresses

    @staticmethod
    def add_new_validator(
        all_validators: List[dict],
        validators: List[dict],
        leader_addresses: set[str],
    ) -> List[dict]:
        """
        Add a new validator to the list of validators.

        Args:
            all_validators (List[dict]): List of all validators.
            validators (List[dict]): List of validators.
            leader_addresses (set[str]): Set of leader addresses.

        Returns:
            List[dict]: Updated list of validators.

        Raises:
            ValueError: If no more validators are available to add.
        """
        if len(leader_addresses) + len(validators) >= len(all_validators):
            raise ValueError("No more validators found to add a new validator")

        addresses = {validator["address"] for validator in validators}
        addresses.update(leader_addresses)

        not_used_validators = [
            validator
            for validator in all_validators
            if validator["address"] not in addresses
        ]

        new_validator = get_validators_for_transaction(not_used_validators, 1)
        return new_validator + validators
