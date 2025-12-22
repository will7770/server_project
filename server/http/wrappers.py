import typing
from ..sock import SocketReader
from ..errors import ClientDisconnect




class FileWrapper:
    def __init__(self, filelike: typing.BinaryIO, chunksize: int = 8192):
        if not hasattr(filelike, 'read'):
            raise ValueError('Argument passed into file_wrapper must be a file-like object')

        self.filelike = filelike
        self.chunk = chunksize
        if hasattr(self.filelike, 'close'):
            self.close = self.filelike.close


    def __iter__(self):
        return self
    

    def __next__(self):
        data = self.filelike.read(self.chunk)
        if not data:
            raise StopIteration
        
        
        
class BodyWrapper:
    __slots__ = ('reader', 'content_len')
    
    def __init__(self, reader: SocketReader, content_len: int = None):
        self.reader = reader
        self.content_len = content_len
        
        
    def read(self, length: int = -1) -> bytearray:
        if length < -1:
            raise TypeError("Length arg cant be less than -1")
        elif length == 0:
            return bytearray()
        
        buf = bytearray()
        
        if length == -1:
            recv_limit = self.content_len
        else:
            recv_limit = min(self.content_len, length)
        
        self._read_into(buf, recv_limit)
        self.content_len -= len(buf)
        return buf
        
    
    def readline(self, size=None) -> bytes:
        buf = bytearray()
        recv_limit = min(self.content_len, 8192)
        while b"\n" not in buf:
            self._read_into(buf, recv_limit)
        
        self.content_len -= len(buf)
        
        idx = buf.find(b"\n")
        if idx == -1:
            return bytes(buf)
        
        self.reader.put_back(buf, start=idx+1)
        return bytes(buf[:idx+1])
    
    
    def readlines(self, sizehint=None) -> list[bytes]:
        if sizehint < -1:
            raise TypeError("Sizehint arg cannot be less than -1")
        if sizehint == 0:
            return [b'']
        
        if sizehint == -1:
            recv_limit = self.content_len
        else:
            recv_limit = min(self.content_len, sizehint)
        
        buf = bytearray()
        while len(buf) < recv_limit:
            self._read_into(buf, recv_limit)
            
        self.reader.put_back(buf, start=recv_limit)
        buf = buf[:recv_limit]
        
        return buf.splitlines()
            
        
    def _read_into(self, buf: bytearray, amount: int = -1):
        data = self.reader.read(amount)
        if len(data) == 0:
            raise ClientDisconnect
        buf.extend(data)