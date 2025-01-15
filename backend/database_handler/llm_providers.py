from backend.domain.types import LLMProvider
from backend.node.create_nodes.providers import get_default_providers
from .models import LLMProviderDBModel
from sqlalchemy.orm import Session
from backend.llms import get_llm_plugin
import pprint


class LLMProviderRegistry:
    def __init__(self, session: Session):
        self.session = session

    def reset_defaults(self):
        """Reset all providers to their default values."""
        self.session.query(LLMProviderDBModel).delete()

        providers = get_default_providers()
        for provider in providers:
            self.session.add(_to_db_model(provider))

        self.session.commit()

    def get_all(self) -> list[LLMProvider]:
        return [
            _to_domain(provider)
            for provider in self.session.query(LLMProviderDBModel).all()
        ]

    async def get_all_dict(self) -> list[dict]:
        providers = self.session.query(LLMProviderDBModel).all()
        result = []

        for provider in providers:
            domain_provider = _to_domain(provider)
            provider_dict = domain_provider.__dict__

            plugin = await get_llm_plugin(
                domain_provider.plugin, domain_provider.plugin_config
            )

            provider_dict["is_available"] = await plugin.is_available()
            provider_dict["is_model_available"] = await plugin.is_model_available(
                domain_provider.model
            )

            result.append(provider_dict)

        return result

    def add(self, provider: LLMProvider) -> int:
        model = _to_db_model(provider)
        self.session.add(model)
        self.session.commit()
        return model.id

    def update(self, id: int, provider: LLMProvider):
        self.session.query(LLMProviderDBModel).filter(
            LLMProviderDBModel.id == id
        ).update(
            {
                LLMProviderDBModel.provider: provider.provider,
                LLMProviderDBModel.model: provider.model,
                LLMProviderDBModel.config: provider.config,
                LLMProviderDBModel.plugin: provider.plugin,
                LLMProviderDBModel.plugin_config: provider.plugin_config,
            }
        )
        self.session.commit()

    def delete(self, id: int):
        self.session.query(LLMProviderDBModel).filter(
            LLMProviderDBModel.id == id
        ).delete()
        self.session.commit()


def _to_domain(db_model: LLMProvider) -> LLMProvider:
    return LLMProvider(
        id=db_model.id,
        provider=db_model.provider,
        model=db_model.model,
        config=db_model.config,
        plugin=db_model.plugin,
        plugin_config=db_model.plugin_config,
    )


def _to_db_model(domain: LLMProvider) -> LLMProviderDBModel:
    return LLMProviderDBModel(
        provider=domain.provider,
        model=domain.model,
        config=domain.config,
        plugin=domain.plugin,
        plugin_config=domain.plugin_config,
    )
