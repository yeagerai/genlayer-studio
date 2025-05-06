__all__ = (
    "LLMModule",
    "SimulatorProvider",
)

import typing
import asyncio
import signal
import os
import sys
import dataclasses

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .base import *


@dataclasses.dataclass
class SimulatorProvider:
    id: str
    kind: str
    model: str


def provider_to_url_and_id_and_key(kind: str) -> tuple[str, str, str]:
    match kind:
        case "ollama":
            return "http://ollama:11434", "ollama", "<no-key>"
        case "openai":
            return "https://api.openai.com", "openai-compatible", "OPENAIKEY"
        case "heurist" | "heuristai":
            return (
                "https://llm-gateway.heurist.xyz",
                "openai-compatible",
                "HEURISTAIAPIKEY",
            )
        case "anthropic":
            return "https://api.anthropic.com", "anthropic", "ANTHROPIC_API_KEY"
        case "xai":
            return "https://api.x.ai", "openai-compatible", "XAI_API_KEY"
        case "google":
            return (
                "https://generativelanguage.googleapis.com",
                "google",
                "GEMINI_API_KEY",
            )
    raise ValueError(f"unknown llm kind `{kind}`")


class LLMModule:
    _process: asyncio.subprocess.Process | None

    def __init__(self):
        self.address = f"127.0.0.1:3032"

        self._terminated = False

        self._process = None

        greyboxing_path = Path(__file__).parent.joinpath("greyboxing.lua")

        self._config = ChangedConfigFile("genvm-module-llm.yaml")

        with self._config.change_default() as conf:
            conf["lua_script_path"] = str(greyboxing_path)
            conf["backends"] = {}
            conf["bind_address"] = self.address

        self._config.write_default()

    async def terminate(self):
        if self._terminated:
            return
        self._terminated = True
        await self.stop()
        self._config.terminate()

    def __del__(self):
        if not self._terminated:
            raise Exception("service was not terminated")

    async def stop(self):
        if self._process is not None:
            try:
                self._process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            await self._process.wait()
            self._process = None

    async def restart(self):
        await self.stop()

        exe_path = Path(os.environ["GENVM_BIN"]).joinpath("genvm-module-llm")

        self._process = await asyncio.subprocess.create_subprocess_exec(
            exe_path,
            "--config",
            self._config.new_path,
            "run",
            "--allow-empty-backends",
            stdin=None,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    async def verify_for_read(self):
        if self._process is None:
            raise Exception("process is not started")
        if self._process.returncode is not None:
            raise Exception(f"process is dead {self._process.returncode}")

    async def change_config(self, new_providers: list[SimulatorProvider]):
        await self.stop()

        with self._config.change() as conf:
            for provider in new_providers:
                url, id, key_env = provider_to_url_and_id_and_key(provider.kind)
                conf["backends"][provider.id] = {
                    "host": url,
                    "provider": id,
                    "key": "${ENV[" + key_env + "]}",
                    "models": [provider.model],
                }

        await self.restart()

    async def provider_available(self, provider_kind: str, model: str) -> bool:
        exe_path = Path(os.environ["GENVM_BIN"]).joinpath("genvm-module-llm")

        url, id, key_env = provider_to_url_and_id_and_key(provider_kind)

        proc = await asyncio.subprocess.create_subprocess_exec(
            exe_path,
            "check",
            "--provider",
            id,
            "--host",
            url,
            "--model",
            model,
            "--key",
            "${ENV[" + key_env + "]}",
        )

        return_code = await proc.wait()

        if return_code != 0:
            print(f"failed provider_kind={provider_kind} model={model}")

        return return_code == 0
