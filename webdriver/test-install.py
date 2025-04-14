#!/usr/bin/env python3

import asyncio
import sys
import aiohttp


async def main():
    proc = await asyncio.create_subprocess_exec(
        "chromedriver",
        "--port=1234",
        "--verbose",
        stdout=sys.stdout,
        stderr=sys.stderr,
        stdin=asyncio.subprocess.DEVNULL,
    )

    loaded = False

    async with aiohttp.ClientSession() as session:
        for i in range(5):
            print(f"== checking status {i} ==")
            try:
                async with session.get("http://localhost:1234/status") as response:
                    print(response.status, await response.text())
                    if response.status == 200:
                        print("status=OK")
                        loaded = True
                        break
            except Exception as e:
                print(e)
                print("failed")
                await asyncio.sleep(5)
        if not loaded:
            raise Exception("NOT HEALTHY")
        print("== creating a session ==")
        async with session.post(
            "http://localhost:1234/session",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "chrome",
                        "goog:chromeOptions": {
                            "args": [
                                "--headless",
                                "--no-sandbox",
                                "--disable-dev-shm-usage",
                                "--in-process-gpu",
                                "--disable-gpu",
                            ]
                        },
                    }
                }
            },
        ) as response:
            body = await response.json()
            print(body)
            if response.status != 200:
                raise Exception(f"status={response.status}")
            session_id = body["value"]["sessionId"]

        print("== navigating ==")
        async with session.post(
            f"http://localhost:1234/session/{session_id}/url",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"url": "https://example.org"},
        ) as response:
            body = await response.json()
            print(body)
            if response.status != 200:
                raise Exception(f"status={response.status}")

    proc.kill()
    await proc.wait()


asyncio.run(main())
