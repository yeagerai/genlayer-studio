import pytest
from backend.protocol_rpc.transactions_parser import (
    decode_method_call_data,
    DecodedMethodCallData,
    decode_deployment_data,
    DecodedDeploymentData,
)
from rlp import encode
import backend.node.genvm.origin.calldata as calldata


@pytest.mark.parametrize(
    "data, expected_result",
    [
        (
            [{"method": "__init__", "args": ["John Doe"]}, False],
            DecodedMethodCallData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
        (
            [{"method": "__init__", "args": ["John Doe"]}, True],
            DecodedMethodCallData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=True,
            ),
        ),
        (
            (
                [{"method": "__init__", "args": ["John Doe"]}]
            ),  # Should fallback to default
            DecodedMethodCallData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
    ],
)
def test_decode_method_call_data(data, expected_result):
    encoded = encode([calldata.encode(data[0]), *data[1:]])
    assert decode_method_call_data(encoded) == expected_result


@pytest.mark.parametrize(
    "data, expected_result",
    [
        (
            [
                b"class Test(name: str)",
                {"method": "__init__", "args": ["John Doe"]},
                False,
            ],
            DecodedDeploymentData(
                contract_code=b"class Test(name: str)",
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
        (
            [
                b"class Test(name: str)",
                {"method": "__init__", "args": ["John Doe"]},
                True,
            ],
            DecodedDeploymentData(
                contract_code=b"class Test(name: str)",
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=True,
            ),
        ),
        (
            [b"class Test(name: str)", {"method": "__init__", "args": ["John Doe"]}],
            DecodedDeploymentData(
                contract_code=b"class Test(name: str)",
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
    ],
)
def test_decode_deployment_data(data, expected_result):
    encoded = encode([data[0], calldata.encode(data[1]), *data[2:]])
    assert decode_deployment_data(encoded) == expected_result
