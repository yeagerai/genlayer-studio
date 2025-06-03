user_storage_contract_schema = {
    "id": 1,
    "jsonrpc": "2.0",
    "result": {
        "ctor": {"kwparams": {}, "params": []},
        "methods": {
            "get_account_storage": {
                "kwparams": {},
                "params": [["account_address", "string"]],
                "readonly": True,
                "ret": "string",
            },
            "get_complete_storage": {
                "kwparams": {},
                "params": [],
                "readonly": True,
                "ret": {"$dict": "string"},
            },
            "update_storage": {
                "kwparams": {},
                "params": [["new_storage", "string"]],
                "readonly": False,
                "ret": "null",
            },
        },
    },
}
