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
    get_gen_protocol_version,
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
async def test_get_current_gen_protocol_version():
    get_versions = await get_gen_protocol_version()
    result = get_versions["result"]

    assert isinstance(result, dict), "Result should be a dict"
    assert "genvm_version" in result
    assert "studio_version" in result

    assert result.get("genvm_version") not in ["unknown", "", None]
    assert result.get("studio_version") not in ["unknown", "", None]
