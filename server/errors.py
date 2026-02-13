class ClientException(Exception):
    pass

class ApplicationException(Exception):
    pass

class ClientDisconnect(ClientException):
    pass


class BufferLimitReached(Exception):
    pass


class BufferCantExtend(Exception):
    pass


class IncompleteBufferResponse(Exception):
    def __init__(self):
        super().__init__("Buffer method returned an incomplete response")


class ServerExit(Exception):
    pass


class InvalidAppReturnType(ApplicationException):
    def __init__(self):
        super().__init__("Application must return an iterable of bytestrings (b'')")


class IncorrectWriteArgument(ApplicationException):
    def __init__(self):
        super().__init__("Bytes must be passed into write()")


class FatalConfigException(Exception):
    def __init__(self, message: str):
        super().__init__(f"Server couldnt start because some config options werent resolved: {message}")