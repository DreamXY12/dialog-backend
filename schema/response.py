from typing import List


def base_response(code, msg, data=None):
    if data is None:
        data = []
    result = {
        "code": code,
        "message": msg,
        "data": data
    }
    return result


def success(data=None, msg=''):
    return base_response(200, msg, data)


def fail(code=-1, msg='', data=None):
    return base_response(code, msg, data)
