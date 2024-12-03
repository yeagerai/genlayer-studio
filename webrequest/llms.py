"""
This file contains the plugins (functions) that are used to interact with the different LLMs (Language Model Models) that are used in the system. The plugins are registered in the `get_llm_function` function, which returns the function that corresponds to the plugin name. The plugins are called with the following parameters:

- `node_config`: A dictionary containing the model and configuration to be used.
- `prompt`: The prompt to be sent to the LLM.
- `regex`: A regular expression to be used to stop the LLM.
- `return_streaming_channel`: An optional asyncio.Queue to stream the response.
"""

from typing import Protocol
import os
import re
import json
import aiohttp
import asyncio
from typing import Optional
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk
from anthropic import AsyncAnthropic
from urllib.parse import urljoin

from dotenv import load_dotenv
import requests

load_dotenv()

plugin_config_key = "plugin_config"


async def process_streaming_buffer(buffer: str, chunk: str, regex: str) -> dict:
    updated_buffer = buffer + chunk
    if regex:
        match = re.search(regex, updated_buffer)
        if match:
            full_match = match.group(0)
            return {"stop": True, "match": full_match}
    return {"stop": False, "match": None}


async def stream_http_response(url, data):
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False)
    ) as session:
        async with session.post(url, json=data, ssl=False) as response:
            async for chunk in response.content.iter_any():
                yield chunk


async def call_ollama(
    node_config: dict,
    prompt: str,
    regex: Optional[str],
    return_streaming_channel: Optional[asyncio.Queue],
) -> str:
    url = urljoin(node_config[plugin_config_key]["api_url"], "generate")

    data = {"model": node_config["model"], "prompt": prompt}

    for name, value in node_config["config"].items():
        data[name] = value

    buffer = ""
    async for chunk_json in stream_http_response(url, data):
        chunk = json.loads(chunk_json)
        if return_streaming_channel is not None:
            if not chunk.get("done"):
                await return_streaming_channel.put(chunk)
            else:
                await return_streaming_channel.put({"done": True})
        else:
            if chunk.get("done"):
                return buffer
            result = await process_streaming_buffer(buffer, chunk["response"], regex)
            buffer += chunk["response"]
            if result["stop"]:
                return result["match"]
    assert False


async def call_openai(
    node_config: dict,
    prompt: str,
    regex: Optional[str],
    return_streaming_channel: Optional[asyncio.Queue],
) -> str:
    api_key_env_var = node_config[plugin_config_key]["api_key_env_var"]
    url = node_config[plugin_config_key]["api_url"]
    client = get_openai_client(os.environ[api_key_env_var], url)
    # TODO: OpenAI exceptions need to be caught here
    stream = await get_openai_stream(client, prompt, node_config)

    return await get_openai_output(stream, regex, return_streaming_channel)


def get_openai_client(api_key: str, url: str | None = None) -> AsyncOpenAI:
    openai_client = None
    if url:
        openai_client = AsyncOpenAI(api_key=api_key, base_url=url)
    else:
        openai_client = AsyncOpenAI(api_key=api_key)
    return openai_client


async def get_openai_stream(client: AsyncOpenAI, prompt, node_config):
    config: dict = node_config["config"]
    if "temperature" in config and "max_tokens" in config:
        return await client.chat.completions.create(
            model=node_config["model"],
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
        )
    else:
        return await client.chat.completions.create(
            model=node_config["model"],
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )


async def get_openai_output(
    stream: AsyncStream[ChatCompletionChunk], regex, return_streaming_channel
):
    buffer = ""
    async for chunk in stream:
        chunk_str = chunk.choices[0].delta.content
        if chunk_str is not None:
            if return_streaming_channel is not None:
                await return_streaming_channel.put(chunk_str)
                continue
            result = await process_streaming_buffer(buffer, chunk_str, regex)
            buffer += chunk_str
            if result["stop"]:
                return result["match"]
            else:
                if return_streaming_channel is not None:
                    await return_streaming_channel.put({"done": True})
                if "done" in chunk_str:
                    return buffer
        else:
            break

    return buffer


class Plugin(Protocol):
    def __init__(self, plugin_config: dict): ...

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: Optional[str],
        return_streaming_channel: Optional[asyncio.Queue],
    ) -> str: ...

    def is_available(self) -> bool: ...

    def is_model_available(self, model: str) -> bool: ...


class OllamaPlugin:
    def __init__(self, plugin_config: dict):
        self.url = plugin_config["api_url"]

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: Optional[str],
        return_streaming_channel: Optional[asyncio.Queue],
    ) -> str:
        return await call_ollama(node_config, prompt, regex, return_streaming_channel)

    def is_available(self) -> bool:
        try:
            if requests.get(self.url).status_code == 404:
                return True
        except Exception:
            pass
        return False

    def is_model_available(self, model: str) -> bool:
        endpoint = f"{self.url}/tags"
        ollama_models_result = requests.get(endpoint).json()
        installed_ollama_models = []
        for ollama_model in ollama_models_result["models"]:
            installed_ollama_models.append(ollama_model["name"].split(":")[0])
        return model in installed_ollama_models and self.is_available()


class OpenAIPlugin:
    def __init__(self, plugin_config: dict):
        self.api_key_env_var = plugin_config["api_key_env_var"]

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: Optional[str],
        return_streaming_channel: Optional[asyncio.Queue],
    ) -> str:
        return await call_openai(node_config, prompt, regex, return_streaming_channel)

    def is_available(self) -> bool:
        env_var = os.environ.get(self.api_key_env_var)

        return (
            env_var != None
            and env_var != ""
            and env_var != "<add_your_openai_api_key_here>"
        )

    def is_model_available(self, model: str) -> bool:
        """
        Model checks are done by the shema providers_schema.json
        """
        return self.is_available()


class AnthropicPlugin:
    def __init__(self, plugin_config: dict):
        self.api_key_env_var = plugin_config["api_key_env_var"]
        self.url = plugin_config["api_url"]

    async def call(
        self,
        node_config: dict,
        prompt: str,
        regex: Optional[str],
        return_streaming_channel: Optional[asyncio.Queue],
    ) -> str:
        client: AsyncAnthropic
        if self.url:
            client = AsyncAnthropic(api_key=self.get_api_key(), base_url=self.url)
        else:
            client = AsyncAnthropic(api_key=self.get_api_key())

        if "max_tokens" not in node_config["config"]:
            raise ValueError("`max_tokens` is required for Anthropic")

        buffer = ""

        # Not using `async with` (https://github.com/anthropics/anthropic-sdk-python?tab=readme-ov-file#streaming-helpers) since I get a `'coroutine' object does not support the asynchronous context manager protocol`. Probably related to how the `EquivalencePrinciple` class implements
        stream = await client.messages.create(
            model=node_config["model"],
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            stream=True,
            **node_config[
                "config"
            ],  # max_tokens, temperature, top_k, top_p, timeout, stop_sequences
        )
        async for event in stream:
            if event.type == "content_block_delta":
                buffer += event.delta.text
                if return_streaming_channel is not None:
                    await return_streaming_channel.put(event.text)
                if regex:
                    match = re.search(regex, buffer)
                    if match:
                        return match.group(0)
            elif event.type == "content_block_stop":
                break

        return buffer

    def is_available(self) -> bool:
        env_var = self.get_api_key()

        return env_var != None and env_var != ""

    def is_model_available(self, model: str) -> bool:
        """
        Model checks are done by the shema providers_schema.json
        """
        return self.is_available()

    def get_api_key(self):
        return os.environ.get(self.api_key_env_var)


def get_llm_plugin(plugin: str, plugin_config: dict) -> Plugin:
    """
    Function to register new providers
    """
    plugin_map = {
        "ollama": OllamaPlugin,
        "openai": OpenAIPlugin,
        "anthropic": AnthropicPlugin,
    }

    if plugin not in plugin_map:
        raise ValueError(f"Plugin {plugin} not registered.")

    return plugin_map[plugin](plugin_config)
