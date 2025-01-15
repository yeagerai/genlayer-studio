import asyncio
import aiohttp
from typing import Protocol, Any
import os
import json

_webrequest_url: str = (
    os.environ["WEBREQUESTPROTOCOL"]
    + "://"
    + os.environ["WEBREQUESTHOST"]
    + ":"
    + os.environ["WEBREQUESTPORT"]
)


class Plugin(Protocol):
    def __init__(self, plugin_config: dict): ...

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: str | None,
    ) -> str: ...

    async def is_available(self) -> bool: ...

    async def is_model_available(self, model: str) -> bool: ...


async def _call_jsonrpc(function_name: str, *args) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": function_name,
        "params": [*args],
        "id": 1,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            _webrequest_url + "/api",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        ) as response:
            res = json.loads(await response.text())
            return res["result"]["response"]


class _RemotePlugin(Plugin):
    def __init__(self, id: str):
        self._id = id

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: str | None,
    ) -> str:
        return await _call_jsonrpc(
            "llm_plugin_call", self._id, node_config, prompt, regex
        )

    async def is_available(self) -> bool:
        return await _call_jsonrpc("llm_plugin_is_available", self._id)

    async def is_model_available(self, model: str) -> bool:
        return await _call_jsonrpc("llm_plugin_is_model_available", self._id, model)


async def get_llm_plugin(plugin: str, plugin_config: dict) -> Plugin:
    return _RemotePlugin(await _call_jsonrpc("llm_plugin_get", plugin, plugin_config))
