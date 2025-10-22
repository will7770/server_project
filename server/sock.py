import socket


class BaseSocket:
    def __init__(self, host: str, port: int, backlog: int):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.sock: socket.socket = None

    def init_socket(self):
        # implement this in subclasses cuz basesocket cant accept family and type
        raise NotImplementedError()

    def deploy(self) -> socket.socket:
        self.init_socket()
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.backlog)

        return self.sock
    

class TCPsocket(BaseSocket):
    def init_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
