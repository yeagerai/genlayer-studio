from pathlib import Path
import zipfile
import io
import base64
import pytest
from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    payload,
    post_request_localhost,
    get_contract_transactions_by_address,
)

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
async def test_get_transactions_by_related_contract():
    status_code, contract = await get_contract_transactions_by_address(
        "0xB385a72303b34c298A88D8594713CB6e1BE864a6"
    )
    result = contract["result"]

    assert status_code == 200
    assert isinstance(result, list | None)
    if isinstance(result, list) and len(result) > 0:
        for i in result:
            assert i["type"] in ["deploy", "method"]
            assert "hash" in i.keys()
            assert "status" in i.keys()
            assert isinstance(i["data"], dict)
            assert "created_at" in i.keys()
            assert "decodedData" in i.keys()
