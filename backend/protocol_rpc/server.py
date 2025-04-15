# backend/protocol_rpc/server.py

import os
from os import environ
import threading
import logging
from flask import Flask
from flask_jsonrpc import JSONRPC
from flask_socketio import SocketIO, join_room, leave_room
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.database_handler.llm_providers import LLMProviderRegistry
from backend.protocol_rpc.configuration import GlobalConfiguration
from backend.protocol_rpc.message_handler.base import MessageHandler
from backend.protocol_rpc.endpoints import register_all_rpc_endpoints
from backend.protocol_rpc.validators_init import initialize_validators
from backend.protocol_rpc.transactions_parser import TransactionParser
from dotenv import load_dotenv
import backend.validators as validators
from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.validators_registry import (
    ValidatorsRegistry,
    ModifiableValidatorsRegistry,
)
from backend.database_handler.accounts_manager import AccountsManager
from backend.consensus.base import ConsensusAlgorithm
from backend.database_handler.models import Base
from backend.rollup.consensus_service import ConsensusService

from .aio import *


def get_db_name(database: str) -> str:
    return "genlayer_state" if database == "genlayer" else database


async def create_app():
    # DataBase
    database_name_seed = "genlayer"
    db_uri = f"postgresql+psycopg2://{environ.get('DBUSER')}:{environ.get('DBPASSWORD')}@{environ.get('DBHOST')}/{get_db_name(database_name_seed)}"
    sqlalchemy_db = SQLAlchemy(
        model_class=Base,
        session_options={
            "expire_on_commit": False
        },  # recommended in https://docs.sqlalchemy.org/en/20/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    )

    engine = create_engine(db_uri, echo=True, pool_size=50, max_overflow=50)

    # Flask
    app = Flask("jsonrpc_api")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_ECHO"] = True
    sqlalchemy_db.init_app(app)

    CORS(app, resources={r"/api/*": {"origins": "*"}}, intercept_exceptions=False)
    jsonrpc = JSONRPC(
        app, "/api", enable_web_browsable_api=True
    )  # check it out at http://localhost:4000/api/browse/#/
    socketio = SocketIO(app, cors_allowed_origins="*")
    # Handlers
    msg_handler = MessageHandler(socketio, config=GlobalConfiguration())
    transactions_processor = TransactionsProcessor(sqlalchemy_db.session)
    accounts_manager = AccountsManager(sqlalchemy_db.session)

    # ro_validators_registry: ValidatorsRegistry = ValidatorsRegistry(sqlalchemy_db.session)

    llm_provider_registry = LLMProviderRegistry(sqlalchemy_db.session)
    consensus_service = ConsensusService()
    transactions_parser = TransactionParser(consensus_service)

    initialize_validators_db_session = Session(engine, expire_on_commit=False)
    await initialize_validators(
        os.environ["VALIDATORS_CONFIG_JSON"],
        ModifiableValidatorsRegistry(initialize_validators_db_session),
        AccountsManager(initialize_validators_db_session),
    )
    initialize_validators_db_session.commit()

    validators_manager_db_session = Session(engine, expire_on_commit=False)
    validators_manager = validators.Manager(validators_manager_db_session)
    await validators_manager.restart()

    validators_registry = validators_manager.registry

    consensus = ConsensusAlgorithm(
        lambda: Session(engine, expire_on_commit=False), msg_handler, validators_manager
    )
    return (
        app,
        jsonrpc,
        socketio,
        msg_handler,
        sqlalchemy_db.session,
        accounts_manager,
        transactions_processor,
        validators_registry,
        consensus,
        llm_provider_registry,
        sqlalchemy_db,
        consensus_service,
        transactions_parser,
        validators_manager,
    )


import asyncio

load_dotenv()

(
    app,
    jsonrpc,
    socketio,
    msg_handler,
    request_session,
    accounts_manager,
    transactions_processor,
    validators_registry,
    consensus,
    llm_provider_registry,
    sqlalchemy_db,
    consensus_service,
    transactions_parser,
    validators_manager,
) = MAIN_SERVER_LOOP.run_until_complete(create_app())

register_all_rpc_endpoints(
    jsonrpc,
    msg_handler,
    request_session,
    accounts_manager,
    transactions_processor,
    validators_registry,
    validators_manager,
    llm_provider_registry,
    consensus,
    consensus_service,
    transactions_parser,
)


# This ensures that the transaction is committed or rolled back depending on the success of the request.
# Opinions on whether this is a good practice are divided https://github.com/pallets-eco/flask-sqlalchemy/issues/216
@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        sqlalchemy_db.session.rollback()  # Rollback if there is an exception
    else:
        sqlalchemy_db.session.commit()  # Commit if everything is fine
    sqlalchemy_db.session.remove()  # Remove the session after every request


async def main():
    def run_socketio():
        socketio.run(
            app,
            debug=os.environ["VSCODEDEBUG"] == "false",
            port=os.environ.get("RPCPORT"),
            host="0.0.0.0",
            allow_unsafe_werkzeug=True,
        )

        @socketio.on("subscribe")
        def handle_subscribe(topics):
            for topic in topics:
                join_room(topic)

        @socketio.on("unsubscribe")
        def handle_unsubscribe(topics):
            for topic in topics:
                leave_room(topic)

        logging.getLogger("werkzeug").setLevel(
            os.environ.get("FLASK_LOG_LEVEL", logging.ERROR)
        )

    # Thread for the Flask-SocketIO server
    threading.Thread(target=run_socketio, daemon=True).start()

    stop_event = threading.Event()

    async def convert_future_to_event():
        await MAIN_LOOP_EXITING
        stop_event.set()

    futures = [
        consensus.run_crawl_snapshot_loop(stop_event=stop_event),
        consensus.run_process_pending_transactions_loop(stop_event=stop_event),
        consensus.run_appeal_window_loop(stop_event=stop_event),
        convert_future_to_event(),
    ]

    try:
        await asyncio.wait(
            [asyncio.tasks.create_task(f) for f in futures], return_when="ALL_COMPLETED"
        )
        print("consensus")
    finally:
        print("pre-term")
        await validators_manager.terminate()
        print("awaited termination")


def app_target():
    try:
        MAIN_SERVER_LOOP.run_until_complete(main())
    except BaseException as e:
        MAIN_LOOP_DONE.set_exception(e)
    finally:
        MAIN_LOOP_DONE.set_result(True)


threading.Thread(target=app_target, daemon=True).start()


def atexit_handler():
    print("initiating shutdown")

    def shutdown():
        MAIN_LOOP_EXITING.set_result(True)

    MAIN_SERVER_LOOP.call_soon_threadsafe(shutdown)
    print("awaiting threads")
    MAIN_LOOP_DONE.result()
    print("shutdown done")


import atexit

atexit.register(atexit_handler)
