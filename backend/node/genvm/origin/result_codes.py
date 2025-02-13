from enum import IntEnum


class ResultCode(IntEnum):
    RETURN = 0
    ROLLBACK = 1
    CONTRACT_ERROR = 2
    ERROR = 3
    NONE = 4
    NO_LEADERS = 5


class StorageType(IntEnum):
    DEFAULT = 0
    LATEST_FINAL = 1
    LATEST_NON_FINAL = 2
