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
from dotenv import load_dotenv

from backend.database_handler.transactions_processor import TransactionsProcessor
from backend.database_handler.validators_registry import ValidatorsRegistry
from backend.database_handler.accounts_manager import AccountsManager
from backend.consensus.base import ConsensusAlgorithm
from backend.database_handler.models import Base
from backend.rollup.consensus_service import ConsensusService


def get_db_name(database: str) -> str:
    return "genlayer_state" if database == "genlayer" else database


def create_app():
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
    validators_registry = ValidatorsRegistry(sqlalchemy_db.session)
    llm_provider_registry = LLMProviderRegistry(sqlalchemy_db.session)
    consensus_service = ConsensusService()

    # Initialize validators from environment configuration in a thread
    initialize_validators_db_session = Session(engine, expire_on_commit=False)
    initialize_validators(
        os.getenv("VALIDATORS_CONFIG_JSON"),
        ValidatorsRegistry(initialize_validators_db_session),
        AccountsManager(initialize_validators_db_session),
    )
    initialize_validators_db_session.commit()

    consensus = ConsensusAlgorithm(
        lambda: Session(engine, expire_on_commit=False), msg_handler
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
    )


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
) = create_app()
register_all_rpc_endpoints(
    jsonrpc,
    msg_handler,
    request_session,
    accounts_manager,
    transactions_processor,
    validators_registry,
    llm_provider_registry,
    consensus,
    consensus_service,
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
thread_socketio = threading.Thread(target=run_socketio)
thread_socketio.start()

# Thread for the crawl_snapshot method
thread_crawl_snapshot = threading.Thread(target=consensus.run_crawl_snapshot_loop)
thread_crawl_snapshot.start()

# Thread for the run_consensus method
thread_consensus = threading.Thread(target=consensus.run_consensus_loop)
thread_consensus.start()

# Thread for the appeal_window method
thread_consensus = threading.Thread(target=consensus.run_appeal_window_loop)
thread_consensus.start()
