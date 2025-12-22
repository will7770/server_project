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
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 0)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(0)



def create_sockets(addresses: list[tuple[str, str]], backlog: int):
    sockets = []
    for pair in addresses:
        host, port = pair
        sockets.append(TCPsocket(host, port, backlog).deploy())
    return sockets



class SocketReader:
    __slots__ = ('sock', 'buf', 'chunksize')
    
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = bytearray()
        self.chunksize: int = 8192

    
    def read(self, amount: int = -1) -> bytearray:
        if amount < -1:
            raise TypeError('Amount cannot be less than -1')
        if amount == 0:
            return bytearray()

        # No amount = get data once
        if amount == -1:
            if not len(self.buf) > 0:   
                self._read(self.chunksize) 
            res = self.buf
            self.buf = bytearray()
            return res

        # Buffer has all data we need
        if len(self.buf) >= amount:
            data = self.buf[:amount]
            del self.buf[:amount]
            return data
        
        # Not enough to satisfy the amount
        size = min(self.chunksize, amount)
        while len(self.buf) < amount:
            received = self._read(size)
            if received == 0:
                data = self.buf
                self.buf = bytearray()
                return data
        
        data = self.buf[:amount]
        del self.buf[:amount]
        return data
    

    def _read(self, size: int):
        data = self.sock.recv(size)
        if data == b'':
            return 0
        self.buf.extend(data)
        return len(data)


    def put_back(self, data: bytes | bytearray, start: int = 0, end: int = -1):
        if start > end and end > -1 and start > 0:
            raise ValueError("Start argument must be less the than end argument.")
        
        view = memoryview(data)
        if end == -1:
            view = view[start:]
        else:
            view = view[start:end]
            
        self.buf[:0] = view
        view.release()