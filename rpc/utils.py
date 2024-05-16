from os import environ
import re
import string
import random

from dotenv import load_dotenv

load_dotenv()

# TODO: Depreacheate (unused)
def get_rpc_url():
    return environ.get('RPCPROTOCOL')+"://localhost:"+environ.get('RPCPORT')+"/api"

# TODO: Depreacheate (common/address.py)
def create_new_address() -> str:
    new_address = ''.join(random.choice(string.hexdigits) for _ in range(40))
    return '0x' + new_address

# TODO: Depreacheate (common/address.py)
def address_is_in_correct_format(address:str) -> bool:
    pattern = r'^0x['+string.hexdigits+']{40}$'
    if re.fullmatch(pattern, address):
        return True
    return False

# TODO: Depreacheate (unused)
def error_response(message:str) -> dict:
    return response_format('error', message=message)

# TODO: Depreacheate (unused)
def success_response(data) -> dict:
    return response_format('success', data=data)

# TODO: Depreacheate (unused)
def response_format(status:str, message:str='', data={}) -> dict:
    return {
        'status': status,
        'message': message,
        'data': data
    }