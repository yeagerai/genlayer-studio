call_contract_function_response = {
    "consensus_data": {
        "leader_receipt": [
            {
                "result": str,
                "calldata": str,
                "contract_state": dict,
                "eq_outputs": dict,
                "execution_result": str,
                "gas_used": int,
                "mode": str,
                "node_config": {
                    "address": str,
                    "config": dict,
                    "model": str,
                    "provider": str,
                    "stake": int,
                    "plugin": str,
                    "plugin_config": dict,
                },
                "vote": str,
            },
            {
                "result": str,
                "calldata": str,
                "contract_state": dict,
                "eq_outputs": dict,
                "execution_result": str,
                "gas_used": int,
                "mode": str,
                "node_config": {
                    "address": str,
                    "config": dict,
                    "model": str,
                    "provider": str,
                    "stake": int,
                    "plugin": str,
                    "plugin_config": dict,
                },
                "vote": str,
            },
        ],
        "validators": list,
        "votes": dict,
    },
    "created_at": str,
    "data": {
        "calldata": str,
    },
    "from_address": str,
    "hash": str,
    "status": str,
    "to_address": str,
    "type": int,
    "value": int,
}
