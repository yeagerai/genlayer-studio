import secrets
from typing import Callable, Awaitable
from numpy.random import default_rng

from dotenv import load_dotenv

from backend.domain.types import LLMProvider

load_dotenv()
rng = default_rng(secrets.randbits(128))


async def random_validator_config(
    get_stored_providers: Callable[[], list[LLMProvider]],
    check_llm_provider: Callable[[LLMProvider], Awaitable[bool]],
    limit_providers: set[str] | None = None,
    limit_models: set[str] | None = None,
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

    providers_to_use = [
        plug for plug in providers_to_use if await check_llm_provider(plug)
    ]

    if not providers_to_use:
        raise Exception("No providers available.")

    return list(rng.choice(providers_to_use, amount))
