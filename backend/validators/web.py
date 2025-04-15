import typing
import asyncio
import signal
import os
import io
import tempfile
import sys
import dataclasses

from pathlib import Path
from copy import deepcopy

from .base import *


class WebModule:
    _process: asyncio.subprocess.Process | None

    def __init__(self):
        self.address = f"127.0.0.1:3031"

        self._terminated = False

        self._process = None

        self._config = ChangedConfigFile("genvm-module-web.yaml")

        with self._config.change_default() as conf:
            conf["webdriver_host"] = (
                f"{os.getenv('WEBDRIVERPROTOCOL', 'http')}://{os.environ['WEBDRIVERHOST']}:{os.environ['WEBDRIVERPORT']}"
            )
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

    async def restart(self):
        await self.stop()

        exe_path = Path(os.environ["GENVM_BIN"]).joinpath("genvm-module-web")

        self._process = await asyncio.subprocess.create_subprocess_exec(
            exe_path,
            "--config",
            self._config.new_path,
            stdin=None,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    async def stop(self):
        if self._process is not None:
            try:
                self._process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            await self._process.wait()
            self._process = None

    async def verify_for_read(self):
        if self._process is None:
            raise Exception("process is not started")
        if self._process.returncode is not None:
            raise Exception(f"process is dead {self._process.returncode}")
