# rpc/endpoint_generator.py

import inspect
from typing import Callable
from flask_jsonrpc import JSONRPC
import flask
from flask_jsonrpc.exceptions import JSONRPCError
from functools import partial, wraps

from backend.protocol_rpc.message_handler.base import MessageHandler


def get_json_rpc_method_name(function: Callable, method_name: str | None = None):
    if method_name is None:
        if isinstance(function, partial):
            return function.func.__name__
        else:
            return function.__name__
    return method_name


def get_function_annotations(function: Callable) -> Callable:
    original_function_annotations = (
        function.func.__annotations__
        if isinstance(function, partial)
        else function.__annotations__
    )
    return {k: v for k, v in original_function_annotations.items()}


def generate_rpc_endpoint(
    jsonrpc: JSONRPC,
    msg_handler: MessageHandler,
    partial_function: Callable,
    method_name: str = None,
) -> Callable:
    json_rpc_method_name = get_json_rpc_method_name(partial_function, method_name)
    partial_function.__name__ = json_rpc_method_name
    partial_function.__annotations__ = get_function_annotations(partial_function)

    @wraps(partial_function)
    async def endpoint(*endpoint_args, **endpoint_kwargs):
        try:
            result = partial_function(*endpoint_args, **endpoint_kwargs)
            if hasattr(result, "__await__"):
                result = await result
            return _serialize(result)

        except JSONRPCError as e:
            raise e
        except Exception as e:
            raise JSONRPCError(code=-32000, message=str(e))

    endpoint = msg_handler.log_endpoint_info(endpoint)
    endpoint = jsonrpc.method(json_rpc_method_name)(endpoint)

    return endpoint


def _serialize(obj):
    """
    Serialize the object to a JSON-compatible format.
    - Convert tuple to list
    - Serialize dict
    - Serialize object
    - Fallback to string
    """
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]  # Convert tuple to list
    elif isinstance(obj, dict):
        return {_serialize(key): _serialize(value) for key, value in obj.items()}
    elif hasattr(obj, "__dict__"):
        return _serialize(obj.__dict__)
    else:  # Fallback
        return str(obj)
