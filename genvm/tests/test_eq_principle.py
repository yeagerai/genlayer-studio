import pytest

from icontract_for_testing import TestContract

from dotenv import load_dotenv
load_dotenv()


## Test Eq Principle ###


def test_call_function_in_icontract_that_doesnt_exist():
    test_contract = TestContract()
    try:
        test_contract.this_method_does_not_exist()
    except AttributeError as ae:
        assert str(ae) == "'WrappedClass' object has no attribute 'this_method_does_not_exist'"

def test_self_query_webpage():
    test_contract = TestContract()
    try:
        test_contract.unittest_method_self_query_webpage()
    except AttributeError as ae:
        assert str(ae) == "'WrappedClass' object has no attribute 'query_webpage'"

def test_self_call_llm():
    test_contract = TestContract()
    try:
        test_contract.unittest_method_self_call_llm()
    except AttributeError as ae:
        assert str(ae) == "'WrappedClass' object has no attribute 'call_llm'"

def test_eq_principle_query_webpage():
    test_contract = TestContract()
    try:
        test_contract.unittest_method_eq_principle_query_webpage()
    except RuntimeError as runerr:
        assert str(runerr) == "Methods of EquivalencePrinciple must be called inside a 'with' block."

def test_eq_principle_call_llm():
    test_contract = TestContract()
    try:
        test_contract.unittest_method_eq_principle_call_llm()
    except RuntimeError as runerr:
        assert str(runerr) == "Methods of EquivalencePrinciple must be called inside a 'with' block."


## Test iContract Methods ###

@pytest.mark.asyncio
async def test_with_eq_principle_calls_icontract__query_webpage():
    test_contract = TestContract()
    result = await test_contract.unittest_method_with_eq_principle_query_webpage()
    assert result == "icontract._query_webpage()"

@pytest.mark.asyncio
async def test_with_eq_principle_calls_icontract__call_llm():
    test_contract = TestContract()
    result = await test_contract.unittest_method_with_eq_principle_call_llm()
    assert result == "icontract._call_llm()"
