"""
These are integration tests for the LLM Plugins
These tests are not intended to test the actual LLMs, but the plugins that interact with them
These tests will incur costs when LLM services are called
The purpose of these tests is to have a small feedback loop for developing the LLM plugins
"""

import asyncio

import pytest
from webrequest.llms import AnthropicPlugin, OllamaPlugin, OpenAIPlugin


def test_openai_plugin():
    plugin_config = {"api_key_env_var": "OPENAIKEY", "api_url": None}
    node_config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "config": {"temperature": 0, "max_tokens": 10},
        "plugin_config": plugin_config,
    }

    plugin = OpenAIPlugin(plugin_config)
    result = asyncio.run(
        plugin.call(
            node_config=node_config,
            prompt="Once upon a time",
            regex=None,
            return_streaming_channel=None,
        )
    )

    print(result)
    assert result != None and result != "" and isinstance(result, str)


@pytest.mark.parametrize(
    "model",
    [
        "mistralai/mixtral-8x22b-instruct",
        "meta-llama/llama-3.1-405b-instruct",
        "meta-llama/llama-3-70b-instruct",
    ],
)
def test_heuristai_plugin(model):
    plugin_config = {
        "api_key_env_var": "HEURISTAIAPIKEY",
        "api_url": "https://llm-gateway.heurist.xyz",
    }
    node_config = {
        "provider": "heuristai",
        "model": model,
        "config": {"temperature": 0, "max_tokens": 10},
        "plugin_config": plugin_config,
    }

    plugin = OpenAIPlugin(plugin_config)
    result = asyncio.run(
        plugin.call(
            node_config=node_config,
            prompt="Once upon a time",
            regex=None,
            return_streaming_channel=None,
        )
    )

    print(result)
    assert result != None and result != "" and isinstance(result, str)


def test_ollama_plugin():
    plugin_config = {
        "api_url": "http://localhost:11434/api/",
    }
    node_config = {
        "provider": "ollama",
        "model": "llama3",
        "config": {
            "mirostat": 0,
            "mirostat_eta": 0.1,
            "microstat_tau": 5,
            "num_ctx": 2048,
            "num_qga": 8,
            "num_gpu": 0,
            "num_thread": 2,
            "repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "temprature": 0.8,
            "seed": 0,
            "stop": "",
            "tfs_z": 1.0,
            "num_predict": 128,
            "top_k": 40,
            "top_p": 0.9,
        },
        "plugin_config": plugin_config,
    }

    plugin = OllamaPlugin(plugin_config)
    result = asyncio.run(
        plugin.call(
            node_config=node_config,
            prompt="Once upon a time",
            regex=None,
            return_streaming_channel=None,
        )
    )

    print(result)
    assert result != None and result != "" and isinstance(result, str)


@pytest.mark.asyncio
async def test_anthropic_plugin():
    plugin_config = {"api_key_env_var": "ANTHROPIC_API_KEY", "api_url": None}
    node_config = {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20240620",
        "config": {"max_tokens": 10},
        "plugin_config": plugin_config,
    }

    plugin = AnthropicPlugin(plugin_config)
    result = await plugin.call(
        node_config=node_config,
        prompt="Once upon a time",
        regex=None,
        return_streaming_channel=None,
    )

    print(result)
    assert result != None and result != "" and isinstance(result, str)
