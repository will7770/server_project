import typing
from ..sock import SocketReader
from ..errors import ClientDisconnect
from collections.abc import Buffer




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
        

        left_to_read = recv_limit
        # TODO: its a bad idea to prealloc big amounts
        ret = bytearray(min(left_to_read, self.reader.max_buf_size))
        ptr = 0
        # Minimize every socket call by maximizing chunk length. Save the original reader's read limit to assign it back later.
        prev_limit = self.reader.chunksize
        
        try:
            self.reader.chunksize = self.reader.max_buf_size
            while left_to_read:
                with memoryview(ret)[ptr:] as view:
                    howmuch = self.reader.read_into(usrbuf=view, amount=left_to_read)
                    
                if not howmuch:
                    raise ClientDisconnect
                
                left_to_read -= howmuch
                ptr += howmuch
                
                # Check if the buffer needs to get extended. We double it if we have more than len(buf)*2 left to read
                # Or we extend it by whatever amount we have left to read if it has less
                space_left = len(ret)-ptr
                if left_to_read > space_left:
                    if left_to_read > len(ret)*2:
                        ret.extend(bytearray(len(ret)))
                    else:
                        ret.extend(bytearray(left_to_read))
        finally:
            self.reader.chunksize = prev_limit
            
        self.content_len -= len(ret)
        return ret
        

    def readinto(self, buf: Buffer) -> int:
        length = len(buf)

        if length == 0:
            return 0
        
        recv_limit = min(self.content_len, length)
        if recv_limit <= 0:
            return 0
        
        left_to_read = recv_limit
        pos = 0
        prev_limit = self.reader.chunksize
        
        try:
            self.reader.chunksize = min(left_to_read, self.reader.max_buf_size)
            while left_to_read:
                with memoryview(buf)[pos:] as view:
                    howmuch = self.reader.read_into(view, left_to_read)
                if not howmuch:
                    raise ClientDisconnect

                pos += howmuch
                left_to_read -= howmuch
                self.content_len -= howmuch
        finally:
            self.reader.chunksize = prev_limit
        
        return recv_limit-left_to_read
    
    
    def readline(self, size = None) -> bytes:
        if size == 0 or self.content_len == 0:
            return b""
        
        size = self.content_len if size is None or size < 0 else min(self.content_len, size)
        
        
        while True:
            idx = self.reader.find(b"\n")
            
            if idx >= 0:
                ret = self.reader.read_until(idx)
                
                self.content_len -= len(ret)
                return bytes(ret)
            
            self.reader.fill(min(1024, size))
    
    
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
            