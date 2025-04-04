from pathlib import Path
import zipfile
import io
import base64
import pytest
from regex import P
from backend.database_handler.errors import AccountNotFoundError
from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    payload,
    post_request_localhost,
    get_contract_by_address,
)
from unittest.mock import patch, AsyncMock
from tests.common.response import (
    assert_dict_struct,
    assert_dict_exact,
    has_success_status,
)

from tests.common.request import call_contract_method

cur_dir = Path(__file__).parent


def test_deploy(setup_validators, from_account):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zip:
        zip.write(cur_dir.joinpath("src", "__init__.py"), "contract/__init__.py")
        zip.write(cur_dir.joinpath("src", "other.py"), "contract/other.py")
        zip.write(cur_dir.joinpath("src", "runner.json"), "runner.json")
    buffer.flush()
    contract_code = buffer.getvalue()

    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account, contract_code, []
    )
    assert has_success_status(transaction_response_deploy)

    # we need to wait for deployment, to do so let's put one more transaction to the queue
    # then it (likely?) will be ordered after subsequent deploy_contract
    wait_response = write_intelligent_contract(
        from_account, contract_address, "wait", []
    )
    assert has_success_status(wait_response)

    res = call_contract_method(contract_address, from_account, "test", [])

    assert res == "123"


@pytest.mark.asyncio
async def test_get_contract_by_address_invalid():
    address = "test_address"
    status_code, _ = await get_contract_by_address(address)

    assert status_code == 400


@pytest.mark.asyncio
async def test_get_contract_by_address_not_exist():
    address = "0x9C778c9688dAA91FDa539399B817C8732c284F18"
    status = 200
    mock_response = (status, {"result": None})

    with patch(
        "tests.common.request.get_contract_by_address", new_callable=AsyncMock
    ) as mock_get_contract:
        mock_get_contract.return_value = mock_response
        status_code, contract = await get_contract_by_address(address)
        result = contract.get("result")

        assert status_code == status
        assert result is None


@pytest.mark.asyncio
async def test_get_contract_by_address_valid():
    address = "0x9C778c9688dAA91FDa539399B817C8732c284F19"
    status = 200
    mock_response = {"result": {"contract_code": "mocked_code"}}

    with patch(
        "path.to.your.module.get_contract_by_address", new_callable=AsyncMock
    ) as mock_get_contract:
        mock_get_contract.return_value = (status, mock_response)
        status_code, contract = await get_contract_by_address(address)
        result = contract.get("result")

        assert status_code == status
        assert isinstance(result, dict)
        assert "contract_code" in result.keys()
