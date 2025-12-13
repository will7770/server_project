import socket
from .errors import ClientDisconnect


class BaseSocket:
    def __init__(self, host: str, port: int, backlog: int):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.sock: socket.socket = None


    def init_socket(self):
        raise NotImplementedError()


    def deploy(self) -> socket.socket:
        self.init_socket()
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.backlog)

        return self.sock
    
    

class TCPsocket(BaseSocket):
    def init_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)



def create_sockets(addresses: list[tuple[str, str]], backlog: int):
    sockets = []
    for pair in addresses:
        host, port = pair
        sockets.append(TCPsocket(host, port, backlog).deploy())
    return sockets



class SocketReader:
    __slots__ = ('sock', 'buf')
    
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = bytearray()

    
    def read(self, amount: int = -1) -> bytearray:
        if amount < -1:
            raise TypeError('Amount cannot be less than -1')
        if amount == 0:
            return bytearray()
        
        if amount == -1:
            if len(self.buf):
                r = self.buf
                self.buf = bytearray()
                return r
            else:
                self._read()
                r = self.buf
                self.buf = bytearray()
                return r
        
        if len(self.buf) >= amount:
            data = self.buf[:amount]
            del self.buf[:amount]
            return data
        
        while len(self.buf) < amount:
            self._read()
        
        data = self.buf[:amount]
        del self.buf[:amount]
        return data
    

    def _read(self, size: int = 8192):
        data = self.sock.recv(size)
        if data == b'':
            raise ClientDisconnect
        self.buf.extend(data)

    
    def put_back(self, data: bytes | bytearray):
        self.buf[:0] = data