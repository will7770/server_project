class RequestBuildingError(Exception):
    pass

class UnsupportedOperation(RequestBuildingError):
    pass


class MalformedRequestLineError(RequestBuildingError):
    def __init__(self, line: bytes):
        self.line = line
        super().__init__(f"Malformed request line {line}")


class IncorrectMethodError(RequestBuildingError):
    def __init__(self, method: str):
        super().__init__(f"Incorrect http method {method}")


class UnsupportedOrIncorrectHTTPVersion(UnsupportedOperation):
    def __init__(self, version: str):
        super().__init__(f"Your http version ({version}) is incorrect or unsupported. Currently supporting version <= HTTP/1.1")


class UnsupportedEncoding(UnsupportedOperation):
    def __init__(self, encodings: list[str]):
        super().__init__(f"Received unsupported encodings: {', '.join(encodings)}. Only supporting chunked.")


class IncorrectHeader(RequestBuildingError):
    def __init__(self, header: str):
        super().__init__(f"Header {header} is incorrect")


class BadHeaderValue(RequestBuildingError):
    def __init__(self, header: str):
        super().__init__(f"Header {header} contains a bad or unsupported value")


class IncorrectHeadersFormat(RequestBuildingError):
    def __init__(self, headers: bytes | str):
        self.headers = headers
        super().__init__(f"Incorrect header format {headers}")


class DuplicateHeader(RequestBuildingError):
    def __init__(self, header: str):
        super().__init__(f"Duplicate header {header}")


class HeaderOverflow(RequestBuildingError):
    def __init__(self, message: str, size: int):
        self.size = size
        super().__init__(f"{message} ({size})")
        
        
class RequestLineOverflow(RequestBuildingError):
    def __init__(self, size: int):
        super().__init__(f"Request line size limit exceeded ({size})")