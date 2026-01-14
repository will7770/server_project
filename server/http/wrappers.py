import typing
from ..sock import SocketReader
from ..errors import ClientDisconnect




class FileWrapper:
    def __init__(self, filelike: typing.BinaryIO, chunksize: int = 8192):
        if not hasattr(filelike, 'read'):
            raise ValueError('Argument must be a file-like object')

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
        
        if length == -1:
            recv_limit = self.content_len
        else:
            recv_limit = min(self.content_len, length)
        if recv_limit <= 0:
            return bytearray()
        
        ret = self.reader.read_exact(amount=recv_limit)
        self.content_len -= len(ret)

        return ret
        
    
    def readline(self, size = None) -> bytes:
        if size == 0 or self.content_len == 0:
            return b""
        
        size = self.content_len if size is None or size < 0 else min(self.content_len, size)
        
        buf = bytearray()
        
        while True:
            idx = buf.find(b"\n", 0, size)
            idx = idx + 1 if idx >= 0 else size if len(buf) >= size else 0
            
            if idx:
                ret = buf[:idx]
                if len(buf) > idx:
                    self.reader.reverse(len(buf)-idx)
                
                self.content_len -= len(ret)
                return bytes(ret)
            
            self.reader.read_exact(min(1024, size))
    
    
    def readlines(self, sizehint=0) -> list[bytes]:
        if self.content_len == 0:
            return []
        
        ret = []
        received = 0
        while True:
            line = self.readline()
            
            if line == b'':
                break
            if (received + len(line)) >= sizehint and sizehint > 0:
                ret.append(line)
                break
            
            ret.append(line)
            received += len(line)
        
        return ret
            