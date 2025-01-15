import secrets
from typing import Callable, Awaitable
from numpy.random import default_rng

from dotenv import load_dotenv

from backend.domain.types import LLMProvider
from backend.llms import Plugin

load_dotenv()
rng = default_rng(secrets.randbits(128))


async def random_validator_config(
    get_stored_providers: Callable[[], list[LLMProvider]],
    get_llm_plugin: Callable[[str, dict], Awaitable[Plugin]],
    limit_providers: set[str] = None,
    limit_models: set[str] = None,
    amount: int = 1,
) -> list[LLMProvider]:
    providers_to_use = get_stored_providers()

    if limit_providers:
        providers_to_use = [
            provider
            for provider in providers_to_use
            if provider.provider in limit_providers
        ]

    if limit_models:
        providers_to_use = [
            provider for provider in providers_to_use if provider.model in limit_models
        ]

    if not providers_to_use:
        raise ValueError(
            f"Requested providers '{limit_providers}' do not match any stored providers. Please review your stored providers."
        )

    async def filter_by_available(provider: LLMProvider) -> bool:
        plugin = await get_llm_plugin(provider.plugin, provider.plugin_config)
        if not await plugin.is_available():
            return False

        if not await plugin.is_model_available(provider.model):
            return False

        return True

    providers_to_use = [
        plug for plug in providers_to_use if await filter_by_available(plug)
    ]

    if not providers_to_use:
        raise Exception("No providers available.")

    return list(rng.choice(providers_to_use, amount))
