import re
import os
import json
from typing import Any
from math import ceil, floor
from flask import Flask
from flask_jsonrpc import JSONRPC
from urllib.parse import urlparse
from time import time

import llms

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv

load_dotenv()

app = Flask("genvm_api")
jsonrpc = JSONRPC(app, "/api", enable_web_browsable_api=True)


def return_success(data: Any):
    return return_format("success", data)


def return_error(message: str):
    return return_format("error", message)


def return_format(status: str, data: Any):
    return {"status": status, "response": data}


def is_valid_url(url):
    parsed_url = urlparse(url)
    return all([parsed_url.scheme, parsed_url.netloc])


def execution_time(start_time, end_time):
    print(f"Execution time: {end_time-start_time:.2f}s")


_cached_plugins: dict[str, llms.Plugin] = {}


@jsonrpc.method("llm_plugin_get")
def llm_plugin_get(plugin: str, plugin_config: dict) -> dict:
    id = json.dumps({"plugin": plugin, "config": plugin_config}, sort_keys=True)
    got = _cached_plugins.get(id, None)
    if got is None:
        plug = llms.get_llm_plugin(plugin, plugin_config)
        _cached_plugins[id] = plug
    return return_success(id)


@jsonrpc.method("llm_plugin_is_available")
def llm_plugin_is_available(plugin_id: str) -> dict:
    return return_success(_cached_plugins[plugin_id].is_available())


@jsonrpc.method("llm_plugin_is_model_available")
def llm_plugin_is_model_available(plugin_id: str, model: str) -> dict:
    return return_success(_cached_plugins[plugin_id].is_model_available(model))


@jsonrpc.method("llm_plugin_call")
async def llm_plugin_call(
    plugin_id: str,
    node_config: dict,
    prompt: str,
    regex: str | None,
) -> dict:
    return return_success(
        await _cached_plugins[plugin_id].call(node_config, prompt, regex, None)
    )


@jsonrpc.method("status")
async def status(x: str) -> dict:
    return {"pong": x}


@jsonrpc.method("llm_genvm_module_call")
async def llm_genvm_module_call(
    encoded_model: str,
    prompt: str,
    mode: str,
) -> dict:
    obj = json.loads(encoded_model)
    plugin = obj["plugin"]
    plugin_config = obj["plugin_config"]
    id = json.dumps({"plugin": plugin, "config": plugin_config}, sort_keys=True)
    got = _cached_plugins.get(id, None)
    if got is None:
        got = llms.get_llm_plugin(plugin, plugin_config)
        _cached_plugins[id] = got
    res = await got.call(obj, prompt, None, None)
    return return_success(res)


if __name__ == "__main__":
    app.run(debug=True, port=os.environ.get("WEBREQUESTPORT"), host="0.0.0.0")
