#!/usr/bin/env python3

import asyncio
import os
import aiohttp


async def main():
    async with aiohttp.ClientSession() as session:
        port = os.getenv("WEBDRIVERPORT", 4444)
        async with session.get(f"http://localhost:{port}/status") as response:
            print(response.status)
            body = await response.json()
            try:
                if body["value"]["ready"] != True:
                    raise Exception("Not ready")
            except Exception as e:
                print(body)
                raise


asyncio.run(main())
