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