import socket
from .errors import BufferLimitReached, BufferCantExtend
from collections.abc import Buffer


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
    __slots__ = ('sock', 'buf', 'chunksize', 'buflen', 'compact_threshold', 'rptr', 'wptr', 'max_buf_size')
    
    def __init__(self, sock: socket.socket):
        self.sock: socket.socket = sock
        self.chunksize: int = 8192
        self.compact_threshold: int = 8192
        self.rptr: int = 0 # read pointer
        self.wptr: int = 0 # write pointer
        self.buf = bytearray(self.chunksize)
        self.buflen: int = self.chunksize
        self.max_buf_size: int = 1024*64

    
    def advance(self, advance_to: int):
        if advance_to < -1:
            raise BufferError("Cant advance pointer to a negative index")
        if advance_to <= self.wptr:
            self.rptr = advance_to
        else: raise BufferError(f"Cant advance to index {advance_to} as it exceeds readable data ({self.wptr})")
    
    
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
            self.advance(advance_to=self.wptr)
            return ret
            
        # Specified index
        # I figured theres a risk of desync between the index we're reading until and actual data
        # Because when we compact the buffer, that index gets moved. So for convenience, just track amount.
        elif until_index > -1:
            amount_to_read = until_index-self.rptr
            size = min(self.chunksize, amount_to_read)
            
            while self.wptr-self.rptr < amount_to_read:
                howmuch = self.fill(size)
                if howmuch == 0:
                    break

            read = min((self.wptr-self.rptr), amount_to_read)
            ret = self.buf[self.rptr:self.rptr+read]
        
        self.advance(advance_to=self.rptr+len(ret)+additionally_advance)
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

            read = min((self.wptr-self.rptr), amount)
            ret = self.buf[self.rptr:self.rptr+read]

        self.advance(self.rptr+len(ret)+additionally_advance)
        return ret
    
    
    def read_into(self, usrbuf: Buffer, amount: int = -1) -> int:
        if amount < -1:
            raise TypeError("Cannot accept an amount less than -1")     
        if amount == 0:
            return 0
        
        
        if amount == -1:
            usrbuf[:] = self.buf[self.rptr:self.wptr]
            return self.wptr-self.rptr
        
        # Avoid writing over memoryview's length
        if hasattr(usrbuf, 'nbytes'):
            amount = min(usrbuf.nbytes, amount)
            
        while self.wptr-self.rptr < amount:
            howmuch = self.fill(amount)
            if howmuch == 0:
                break
            
        read = min((self.wptr-self.rptr), amount)
        usrbuf[:read] = self.buf[self.rptr:self.rptr+read]
        
        self.advance(self.rptr+read)
        return read
    
    
    def fill(self, size: int = -1) -> int:
        size = size if size != -1 and size <= self.chunksize else self.chunksize
        # check if we need to compact/resize the buffer
        while self.buflen-self.wptr < size:
            try:
                self.rebufferthebuffer()
            except BufferLimitReached:
                return 0 # Signal to stop trying to extend
            except BufferCantExtend:
                break # Keep trying to fill as some space may still be present
        
        
        view = memoryview(self.buf)[self.wptr:]
        received = self.sock.recv_into(view, min(view.nbytes, size))
        if received == 0:
            # TODO: maybe its a good idea to disconnect here?
            return 0
        
        view.release()
        self.wptr += received
        return received

    
    def rebufferthebuffer(self):
        # If read pointer >= effective compact range, we compact
        if self.rptr >= self.compact_threshold:           
            view = memoryview(self.buf)[self.rptr:self.wptr]
            self.buf[:view.nbytes] = view
            self.rptr, self.wptr = 0, view.nbytes
        
        # If the buffer is full from top to bottom or compacting is not worth it, we double
        else:
            if self.wptr == self.max_buf_size:
                raise BufferLimitReached
            elif self.buflen*2 > self.max_buf_size:
                raise BufferCantExtend
            
            self.buf.extend(bytearray(self.buflen))
            self.buflen *= 2