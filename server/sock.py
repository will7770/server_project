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
    __slots__ = ('sock', 'buf', 'chunksize', 'rptr', 'wptr', 'max_buf_size')
    
    def __init__(self, sock: socket.socket):
        self.sock: socket.socket = sock
        self.chunksize: int = 8192
        self.rptr: int = 0 # read pointer
        self.wptr: int = 0 # write pointer
        self.buf = bytearray(self.chunksize)
        self.max_buf_size: int = 65536

    
    def advance(self, advance_to: int):
        if advance_to <= self.wptr and advance_to > -1:
            self.rptr = advance_to
        else: raise BufferError("Cant advance past readable data or accept a negative value")
    
    
    def find(self, bytestring: bytes):
        """ Find and return the position while respecting the read and write pointers """
        return self.buf.find(bytestring, self.rptr, self.wptr)
    
    
    def read_until(self, until_index: int = -1, additionally_advance: int = 0) -> bytearray:
        if until_index < -1:
            raise TypeError('Index cannot be less than -1')
        if until_index == 0:
            return self.buf[self.rptr:self.rptr]

        # Unspecified index
        if until_index == -1:
            ret = self.buf[self.rptr:self.wptr]
            
        # Specified index
        elif until_index > -1:
            size = min(self.chunksize, until_index)
            while self.wptr < until_index:
                howmuch = self.fill(size)
                if howmuch == 0:
                    break
            ret = self.buf[self.rptr:until_index]
        
        self.advance(advance_to=until_index+additionally_advance)
        return ret
    

    def read_exact(self, amount: int, additionally_advance: int = 0):
        if amount < -1:
            raise TypeError("Cannot accept an amount less than -1")
        if amount == 0:
            return bytearray()
        
        # Unspecified amount
        if amount == -1:
            ret = self.buf[self.rptr:self.wptr]
        
        # Specified amount
        elif amount > -1:
            size = min(self.chunksize, amount)
            while self.wptr-self.rptr < amount:
                howmuch = self.fill(size)
                if howmuch == 0:
                    break
            ret = self.buf[self.rptr:self.rptr+amount]

        self.advance(self.rptr+len(ret)+additionally_advance)
        return ret
    
    
    def fill(self, size: int = -1) -> int:
        size = self.chunksize if size == -1 else size
        # check if we need to double the buffer size
        buflen = len(self.buf)
        if buflen-self.wptr <= size:
            if self.max_buf_size > buflen*2:
                self.buf.extend(b"\x00" * buflen)
            else:
                self.rebufferthebuffer()

        view = memoryview(self.buf)[self.wptr:]
        received = self.sock.recv_into(view, size)
        if received == 0:
            return 0
        
        self.wptr += received
        return received
    
    
    def rebufferthebuffer(self):
        view = memoryview(self.buf)[self.rptr:self.wptr]
        self.buf[:view.nbytes] = view
        self.rptr, self.wptr = 0, view.nbytes