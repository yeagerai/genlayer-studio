# tests/e2e/test_storage.py

import eth_utils

from tests.common.request import (
    deploy_intelligent_contract,
    write_intelligent_contract,
    payload,
    post_request_localhost,
    call_contract_method,
)
from tests.integration.contract_examples.mocks.football_prediction_market_get_contract_schema_for_code import (
    football_prediction_market_contract_schema,
)
from tests.integration.contract_examples.mocks.call_contract_function import (
    call_contract_function_response,
)

from tests.common.response import (
    assert_dict_struct,
    assert_dict_exact,
    has_success_status,
)

from tests.integration.conftest import (
    get_prompts_from_contract_code,
)

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading


# class MockWebServer(BaseHTTPRequestHandler):
#     def do_GET(self):
#         print(f"MockWebServer received request for path: {self.path}")
#         print(f"Headers: {self.headers}")

#         mock_response = """
#         <html>
#             <body>
#                 <div>
#                     Georgia 2 - 0 Portugal
#                 </div>
#             </body>
#         </html>
#         """
#         self.send_response(200)
#         self.send_header("Content-type", "text/html")
#         self.end_headers()
#         self.wfile.write(mock_response.encode())
#         print("MockWebServer sent response")


def test_football_prediction_market(from_account, setup_validators):
    # port = 8000
    # mock_server = HTTPServer(("0.0.0.0", port), MockWebServer)
    # server_thread = threading.Thread(target=mock_server.serve_forever)
    # server_thread.daemon = True
    # server_thread.start()
    # print(f"Mock server started on port {port}")  # Debug print

    # try:
    # Get contract schema
    contract_code = open("examples/contracts/football_prediction_market.py", "r").read()
    modified_contract_code = contract_code.replace(
        '"https://www.bbc.com/sport/football/scores-fixtures/" + game_date',
        '"http://nginx-proxy/"',  # Use the service name from docker-compose
    )

    print("modified_contract_code", modified_contract_code)

    # Parse prompts from contract code
    prompts = get_prompts_from_contract_code(modified_contract_code)

    # Mock the validator responses
    responses = {
        prompts[0]: {
            "score": "2:0",
            "winner": 1,
        },
    }
    setup_validators(responses)

    result_schema = post_request_localhost(
        payload(
            "gen_getContractSchemaForCode",
            eth_utils.hexadecimal.encode_hex(modified_contract_code),
        )
    ).json()
    assert has_success_status(result_schema)
    assert_dict_exact(result_schema, football_prediction_market_contract_schema)

    # Deploy Contract
    contract_address, transaction_response_deploy = deploy_intelligent_contract(
        from_account,
        modified_contract_code,
        ["2024-06-26", "Georgia", "Portugal"],
    )
    assert has_success_status(transaction_response_deploy)

    ########################################
    ############# RESOLVE match ############
    ########################################
    transaction_response_call_1 = write_intelligent_contract(
        from_account,
        contract_address,
        "resolve",
        [],
    )
    assert has_success_status(transaction_response_call_1)

    # Assert response format
    assert_dict_struct(transaction_response_call_1, call_contract_function_response)

    # Get Updated State
    contract_state_2 = call_contract_method(
        contract_address, from_account, "get_resolution_data", []
    )

    assert contract_state_2["winner"] == 1
    assert contract_state_2["score"] == "2:0"
    assert contract_state_2["has_resolved"] == True

    # finally:
    #     mock_server.shutdown()
    #     mock_server.server_close()
    #     server_thread.join()
