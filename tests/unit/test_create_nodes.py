import asyncio
from typing import Callable, List, Optional
import pytest
from backend.domain.types import LLMProvider
from backend.node.create_nodes.create_nodes import random_validator_config
from backend.llms import Plugin


def plugin_mock(available: bool, available_models: List[str]) -> Plugin:
    class PluginMock(Plugin):
        def __init__(self, plugin_config: dict):
            pass

        async def call(
            self,
            node_config: dict,
            prompt: str,
            regex: Optional[str],
            return_streaming_channel: Optional[asyncio.Queue],
        ) -> str:
            return ""

        async def is_available(self):
            return available

        async def is_model_available(self, model: str) -> bool:
            return model in available_models and self.is_available()

    return PluginMock({})


@pytest.mark.parametrize(
    "stored_providers,plugins,limit_providers,limit_models,expected",
    [
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                )
            ],
            {"ollama": plugin_mock(True, ["llama3"])},
            None,
            None,
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                )
            ],
            id="only ollama",
        ),
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3.1",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="heuristai",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            {
                "ollama": plugin_mock(True, ["llama3", "llama3.1"]),
                "openai": plugin_mock(False, []),
                "heuristai": plugin_mock(True, ["other"]),
            },
            None,
            None,
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3.1",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                )
            ],
            id="only ollama available",
        ),
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="a",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="b",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="c",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            {
                "ollama": plugin_mock(True, ["llama3", "llama3.1"]),
                "openai": plugin_mock(True, ["gpt-4", "gpt-4o"]),
                "heuristai": plugin_mock(True, ["other"]),
            },
            ["openai"],
            None,
            [
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
            ],
            id="only openai",
        ),
        pytest.param(
            [
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="a",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="b",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            {
                "ollama": plugin_mock(False, ["llama3", "llama3.1"]),
                "openai": plugin_mock(False, ["gpt-4", "gpt-4o"]),
                "heuristai": plugin_mock(True, ["a", "b"]),
            },
            ["heuristai"],
            ["a"],
            [
                LLMProvider(
                    provider="heuristai",
                    model="a",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            id="only heuristai",
        ),
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3.1",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="a",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="b",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            {
                "ollama": plugin_mock(True, ["llama3", "llama3.1"]),
                "openai": plugin_mock(True, ["gpt-4", "gpt-4o"]),
                "heuristai": plugin_mock(True, ["a", "b"]),
            },
            None,
            None,
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3.1",
                    config={},
                    plugin="ollama",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="openai",
                    model="gpt-4o",
                    config={},
                    plugin="openai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="a",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
                LLMProvider(
                    provider="heuristai",
                    model="b",
                    config={},
                    plugin="heuristai",
                    plugin_config={},
                ),
            ],
            id="all available",
        ),
    ],
)
@pytest.mark.asyncio
async def test_random_validator_config(
    stored_providers,
    plugins,
    limit_providers,
    limit_models,
    expected,
):
    async def get_llm_plugin(plugin, config):
        return plugins[plugin]

    result = await random_validator_config(
        lambda: stored_providers,
        get_llm_plugin,
        limit_providers,
        limit_models,
        10,
    )

    result_set = set(result)
    expected_set = set(expected)

    assert result_set.issubset(expected_set)


@pytest.mark.parametrize(
    "stored_providers,plugins,limit_providers,limit_models,exception",
    [
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3",
                    config={},
                    plugin="",
                    plugin_config={},
                )
            ],
            {},
            ["heuristai", "openai"],
            None,
            ValueError,
            id="no match",
        ),
        pytest.param(
            [
                LLMProvider(
                    provider="ollama",
                    model="llama3",
                    config={},
                    plugin="",
                    plugin_config={},
                )
            ],
            {
                "ollama": plugin_mock(False, ["llama3", "llama3.1"]),
                "openai": plugin_mock(True, ["gpt-4", "gpt-4o"]),
                "heuristai": plugin_mock(True, ["a", "b"]),
            },
            ["ollama"],
            None,
            Exception,
            id="no intersection",
        ),
    ],
)
@pytest.mark.asyncio
async def test_random_validator_config_fail(
    stored_providers,
    plugins,
    limit_providers,
    limit_models,
    exception,
):
    with pytest.raises(exception):
        await random_validator_config(
            lambda: stored_providers,
            lambda plugin, config: plugins[plugin],
            limit_providers,
            limit_models,
            10,
        )
