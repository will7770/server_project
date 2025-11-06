class ClientException(Exception):
    pass

class ApplicationException(Exception):
    pass

class ClientDisconnect(ClientException):
    pass


class InvalidAppReturnType(ApplicationException):
    def __init__(self):
        super().__init__("Application must return an iterable of bytestrings (b'')")


class IncorrectWriteInvocation(ApplicationException):
    def __init__(self):
        super().__init__("Bytes must be passed int write()")


class FatalConfigException(Exception):
    def __init__(self, message: str):
        super().__init__("Server couldnt start because some config options werent resolved: %s", message)