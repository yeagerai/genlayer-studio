from enum import IntEnum


class Methods(IntEnum):
    GET_CALLDATA = 0
    GET_CODE = 1
    STORAGE_READ = 2
    STORAGE_WRITE = 3
    CONSUME_RESULT = 4
    GET_LEADER_NONDET_RESULT = 5
    POST_NONDET_RESULT = 6
    POST_MESSAGE = 7
    CONSUME_FUEL = 8
    DEPLOY_CONTRACT = 9
    ETH_CALL = 10
    ETH_SEND = 11
    GET_BALANCE = 12


class Errors(IntEnum):
    OK = 0
    ABSENT = 1
    FORBIDDEN = 2
    I_AM_LEADER = 3
