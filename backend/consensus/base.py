import asyncio
from time import sleep
from backend.node.base import Node
from backend.database_handler.db_client import DBClient
from backend.database_handler.types import ConsensusData
from backend.consensus.vrf import get_validators_for_transaction
from backend.database_handler.chain_snapshot import ChainSnapshot
from backend.database_handler.contract_snapshot import ContractSnapshot
from backend.database_handler.transactions_processor import (
    TransactionsProcessor,
    TransactionStatus,
)


class ConsensusAlgorithm:
    def __init__(
        self, dbclient: DBClient, transactions_processor: TransactionsProcessor
    ):
        self.dbclient = dbclient
        self.transactions_processor = transactions_processor
        self.queues = {}

    def crawl_snapshot(self):
        while True:
            chain_snapshot = ChainSnapshot(self.dbclient)
            pending_transactions = chain_snapshot.get_pending_transactions()
            if len(pending_transactions) > 0:
                for transaction in pending_transactions:
                    contract_address = transaction["to_address"]
                    try:
                        self.queues[contract_address].put(transaction)
                    except KeyError:
                        self.queues[contract_address] = asyncio.Queue()
                        self.queues[contract_address].put(transaction)
            sleep(10)

    def run_consensus(self):
        while True:
            # watch out! as ollama uses GPU resources and webrequest aka selenium uses RAM
            chain_snapshot = ChainSnapshot(self.dbclient)
            loop = asyncio.get_running_loop()
            [
                loop.create_task(
                    self.exec_transaction(self.queues[key].get(), chain_snapshot)
                    if len(self.queues[key]) > 0
                    else ContractSnapshot(
                        key, self.dbclient
                    ).expire_queued_transactions()
                )
                for key in self.queues.keys()
            ]
            sleep(10)

    async def exec_transaction(
        self,
        transaction: dict,
        snapshot: ChainSnapshot,
    ) -> dict:
        # Update transaction status
        self.transactions_processor.update_transaction_status(
            transaction["id"], TransactionStatus.PROPOSING
        )
        # Select Leader and validators
        all_validators = snapshot.get_all_validators()
        leader, remaining_validators = get_validators_for_transaction(
            all_validators, snapshot.num_validators
        )
        num_validators = len(remaining_validators) + 1

        contract_snapshot = ContractSnapshot(transaction["to_address"], self.dbclient)

        # Create Leader
        leader_node = Node(
            contract_snapshot, leader["address"], "leader", leader["config"]
        )

        # Leader executes transaction
        leader_receipt = leader_node.exec_transaction(transaction)
        votes = {leader["address"]: leader_receipt["vote"]}
        # Update transaction status
        self.transactions_processor.update_transaction_status(
            transaction["id"], TransactionStatus.COMMITTING
        )

        # Create Validators
        validator_nodes = [
            Node(
                contract_snapshot,
                validator["address"],
                "validator",
                validator["config"],
                leader_receipt,
            )
            for i, validator in enumerate(remaining_validators)
        ]

        # Validators execute transaction
        validators_results = []
        loop = asyncio.get_running_loop()
        validation_tasks = [
            loop.create_task(
                validator.exec_transaction(transaction)
            )  # watch out! as ollama uses GPU resources and webrequest aka selenium uses RAM
            for validator in validator_nodes
        ]
        validation_results = await asyncio.gather(*validation_tasks)

        for i in range(len(validation_results)):
            votes[f"{validation_results[i]['validator']}"] = validation_results[i][
                "vote"
            ]
        self.transactions_processor.update_transaction_status(
            transaction["id"], TransactionStatus.REVEALING
        )

        if (
            len([vote for vote in votes.values() if vote == "agree"])
            < num_validators // 2
        ):
            raise Exception("Consensus not reached")

        # Temporary to final status until we have appeals
        self.transactions_processor.update_transaction_status(
            transaction["id"], TransactionStatus.FINALIZED
        )

        final = False
        consensus_data = ConsensusData(
            final=final,
            votes=votes,
            leader=leader_receipt,
            validators=validators_results,
        ).model_dump_json()

        execution_output = {}
        execution_output["leader_data"] = leader_receipt
        execution_output["consensus_data"] = consensus_data
        return execution_output
