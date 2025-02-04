import pytest
from unittest.mock import Mock
from backend.protocol_rpc.transactions_parser import (
    TransactionParser,
    DecodedMethodSendData,
    DecodedDeploymentData,
)
from rlp import encode
import backend.node.genvm.origin.calldata as calldata


@pytest.fixture
def transaction_parser():
    # Create a mock ConsensusService
    consensus_service = Mock()
    consensus_service.web3 = Mock()
    return TransactionParser(consensus_service)


@pytest.mark.parametrize(
    "data, expected_result",
    [
        (
            [{"method": "__init__", "args": ["John Doe"]}, False],
            DecodedMethodSendData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
        (
            [{"method": "__init__", "args": ["John Doe"]}, True],
            DecodedMethodSendData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=True,
            ),
        ),
        (
            (
                [{"method": "__init__", "args": ["John Doe"]}]
            ),  # Should fallback to default
            DecodedMethodSendData(
                calldata=b"\x16\x04args\rDJohn Doe\x06methodD__init__",
                leader_only=False,
            ),
        ),
    ],
)
def test_decode_method_send_data(transaction_parser, data, expected_result):
    encoded = encode([calldata.encode(data[0]), *data[1:]])
    assert transaction_parser.decode_method_send_data(encoded.hex()) == expected_result


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
def test_decode_deployment_data(transaction_parser, data, expected_result):
    encoded = encode([data[0], calldata.encode(data[1]), *data[2:]])
    assert transaction_parser.decode_deployment_data(encoded.hex()) == expected_result
