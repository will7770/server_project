import socket


class BaseSocket:
    def __init__(self, family: socket.AddressFamily, type: socket.SocketType, host: str, port: int, backlog: int = 1):
        self.family = family
        self.type = type
        self.host = host
        self.port = port
        self.backlog = backlog
        self.sock = None

    def __enter__(self) -> socket.socket:
        sock = socket.socket(self.family, self.type)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock = sock

        sock.bind((self.host, self.port))
        sock.listen(self.backlog)

        return sock
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.sock.close()
        return 0