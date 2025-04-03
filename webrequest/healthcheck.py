import requests
import os
from dotenv import load_dotenv
import json

load_dotenv(".env.example")
load_dotenv()

_webrequest_url: str = (
    os.environ["WEBREQUESTPROTOCOL"]
    + "://"
    + os.environ["WEBREQUESTHOST"]
    + ":"
    + os.environ["WEBREQUESTPORT"]
)

str_check = "test"
res_llms = requests.post(
    f"{_webrequest_url}/api",
    data=json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "status",
            "params": [str_check],
            "id": 1,
        }
    ),
    headers={"Content-Type": "application/json"},
).json()
if res_llms["result"]["pong"] != str_check:
    print("bad result", res_llms)
    exit(1)
