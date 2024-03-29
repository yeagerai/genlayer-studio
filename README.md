# GenLayer Prototype
## Introduction
Welcome to the GenLayer prototype, the first step towards a decentralized platform that combines the ease of using Python to write contracts, the access to the internet, the intelligence of the LLMs, and the security and efficiency of a blockchain.

## Prototype Components
The GenLayer prototype consists of the following main components:

* **State Storage (PostgreSQL):** We use a SQL database to maintain the blockchain's updated and persistent state.
* **State Manager (JSON-RPC Server):** A backend that processes requests, either to read the state of the blockchain or to execute transactions involving intelligent contracts.
* **Developer Interface:** CLI and some execution scripts to facilitate developers' interaction with the node, allowing the deployment and execution of intelligent contracts.
* **The Consensus Algorithm:** A python routine that launches execution processes into the GenVM, following the approach defined in the whitepaper.
* **Gen Virtual Machine (GenVM):** A Dockerized environment prepared to run intelligent contracts safely.

## Installation

# Window One

```
$ docker-composer up
```

# Window Two

```
$ virtualenv .venv
$ source .venv/bin/activate
(.venv) $ pip install -r rewquirments.txt
(.venv) $ export PYTHONPATH="${PYTHONPATH}:/.../genlayer-prototype"
(.venv) $ python python cli/genlayer.py create-db
(.venv) $ python python cli/genlayer.py create-tables
```

## Nodes

* Run `rpc/server.py` to launch the server on port `4000`.
* Run some CLI commands to create an initial state with validators, and deployed contracts:
    ```
    # python cli/genlayer.py register-validators --count 10 --min-stake 1 --max-stake 10
    ...
    # python cli/genlayer.py create-eoa --balance 10
    ...
    {'id': 1, 'jsonrpc': '2.0', 'result': {'balance': 10.0, 'id': '95594942-17e5-4f91-8862-c3a4eae5b58c', 'status': 'EOA created'}}
    ...
    # python cli/genlayer.py deploy --from-account 95594942-17e5-4f91-8862-c3a4eae5b58c /home/user/Documents/genlayer/genlayer-node-prototype/contracts/wizzard_of_coin.py
    ...
    {{'30a079b5-4615-4b4f-a7c8-807f1f9d1577', 'status': 'deployed'}}
    ```

    That will create an initial state that enables the user to start sending transactions to the network. You can check all the changes on DB with a viewer such as `dbeaver`.

* Execute a transaction. You can use the `scripts/debug_contract.py` there you would see the execution syntax, and you can start creating and debugging intelligent contracts.

From now on you can create new intelligent contracts and test them by executing transactions with this prototype.
