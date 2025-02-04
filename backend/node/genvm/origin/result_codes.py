from enum import IntEnum


class ResultCode(IntEnum):
    RETURN = 0
    ROLLBACK = 1
    NONE = 2
    ERROR = 3
    CONTRACT_ERROR = 4


class StorageType(IntEnum):
    DEFAULT = 0
    LATEST_FINAL = 1
    LATEST_NON_FINAL = 2
