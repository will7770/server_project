class RequestBuildingError(Exception):
    pass


class MalformedRequestLineError(RequestBuildingError):
    def __init__(self, line: bytes):
        self.line = line
        super().__init__(f"Malformed request line {line}")


class IncorrectHeadersFormat(RequestBuildingError):
    def __init__(self, headers: bytes | str):
        self.headers = headers
        super().__init__(f"Incorrect header format {headers}")


class HeaderOverflow(RequestBuildingError):
    def __init__(self, size: int):
        self.size = size
        super().__init__(f"Header size limit exceeded ({size})")