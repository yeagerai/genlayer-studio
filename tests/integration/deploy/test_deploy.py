from pathlib import Path
import zipfile
import io
import base64

from tests.common.request import (
    deploy_intelligent_contract,
    send_transaction,
    payload,
    post_request_localhost,
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
        zip.write(cur_dir.joinpath("src", "__init__.py"), "src/__init__.py")
        zip.write(cur_dir.joinpath("src", "other.py"), "src/other.py")
        zip.write(cur_dir.joinpath("src", "runner.json"), "runner.json")
    buffer.flush()
    contract_code = buffer.getvalue()

    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account, contract_code, []
    )
    assert has_success_status(transaction_response_deploy)

    # we need to wait for deployment, to do so let's put one more transaction to the queue
    # then it (likely?) will be ordered after subsequent deploy_contract
    wait_response = send_transaction(from_account, contract_address, "wait", [])
    assert has_success_status(wait_response)

    res = call_contract_method(contract_address, from_account, "test", [])

    assert res == "123"
