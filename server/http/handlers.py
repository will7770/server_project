import socket
import io
import sys
import typing
from .errors import *
from ..errors import *
import datetime
import re
import mmap



# thanks gunicorn
RFC9110_5_6_2_TOKEN_SPECIALS = r"!#$%&'*+-.^_`|~"
TOKEN_RE = re.compile(r"[%s0-9a-zA-Z]+" % (re.escape(RFC9110_5_6_2_TOKEN_SPECIALS)))

HEADER_VALUE_RE = re.compile(r'[ \t\x21-\x7e\x80-\xff]*')


class Response:
    def __init__(self, sock: socket.socket):
        self.sock: socket.socket = sock
        self.response_length: int = None
        self.status: str = None
        self.headers_sent: bool = False
        self.headers: list[tuple[str, str]] = []
        self.sent: int = 0
        self.body = io.BytesIO()


    def send_headers(self):
        # prepare response
        if self.headers_sent:
            return
        
        response = f"HTTP/1.1 {self.status}\r\n"
        for token, val in self.headers:
            response += f"{token}: {val}\r\n"

        response += "\r\n"
        self.sock.sendall(response.encode())
        self.headers_sent = True


    def start_response(self, status: int, response_headers: list[tuple[str, str]], exc_info = None) -> typing.Callable:
        if exc_info:
            try:
                if self.headers_sent:
                    raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None
        elif self.headers_sent:
            raise AssertionError("Response had already been started")
        
        self.status = status
        self.process_headers(response_headers)
        self.send_headers()
        return self.write


    def write(self, data: bytes):
        self.send_headers()

        if type(data) != bytes:
            try:
                data = data.encode()
            except AttributeError:
                raise IncorrectWriteArgument
        
        datalen = len(data)
        to_send = datalen
        if self.response_length:
            if self.response_length <= self.sent:
                return
            to_send = min(self.response_length-self.sent, to_send)
            to_send = data[:to_send]

        self.sent += len(to_send)
        self.sock.sendall(to_send)


    def handle_app(self, app: typing.Callable, environ: dict):
        app_result = app(environ, self.start_response)
        for chunk in app_result:
            self.write(chunk)
        # some wsgi apps close their resources, return to make it possible
        return app_result
    

    def process_headers(self, headers: list[tuple[str, str]]):
        for token, val in headers:
            if type(token) != str or not TOKEN_RE.fullmatch(token):
                raise IncorrectHeadersFormat(token)
            
            if type(val) != str or not HEADER_VALUE_RE.fullmatch(val):
                raise IncorrectHeadersFormat(val)
            
            ltoken = token.lower()
            if ltoken == 'content-length':
                self.response_length = int(val)

            self.headers.append((token, val))


    def build_environ(self, req) -> dict:
        split_path = (req.path.decode()).split('?')

        if len(split_path) != 2:
            path, query_string = split_path[0], ''
        else:
            path, query_string = split_path

        environ = {
            'REQUEST_METHOD': req.method.decode(),
            'PATH_INFO': path,
            'SERVER_PROTOCOL': req.proto.decode(),
            'QUERY_STRING': query_string,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.file_wrapper': FileWrapper
        }
        # write headers to environ
        for header_pair in req.headers:
            name, value = header_pair
            name = name.replace('-', '_')

            if name == 'Content_Type' or name == 'Content_Length':
                environ[name.upper()] = value.strip()
            else:
                name = 'HTTP_' + name
                environ[name] = value.strip()

        # write body
        environ['wsgi.input'].write(self.body.getbuffer())
        environ['wsgi.input'].seek(0)
        return environ




class Request:
    def __init__(self):
        self.body = io.BytesIO()
        self.bufsize = 8192
        self.content_len = 0
        self.headers = []
        self.max_header_size = 16384
        

    def build_request(self, sock: socket.socket):
        # begin reading request line and headers
        buf = b""
        while b"\r\n\r\n" not in buf:
            if len(buf) > self.max_header_size:
                raise HeaderOverflow(self.max_header_size)
            
            chunk = sock.recv(self.bufsize)
            if chunk == b'':
                raise ClientDisconnect   
            
            buf += chunk
        headers_end = buf.find(b"\r\n\r\n")

        self.parse_request(buf, headers_end)

        # begin body receival
        content_len = self.content_len
        body = self.body
        # check if there's any useful data for body in buffer
        if len(buf[headers_end+4:]) > 0:
            body.write(buf[headers_end+4:])

        while body.getbuffer().nbytes < content_len:
            to_recv = content_len - body.getbuffer().nbytes
            chunk = sock.recv(min(self.bufsize, to_recv))

            if chunk == b'':
                raise ClientDisconnect
            
            body.write(chunk)
        
    
    def parse_request(self, buf: bytes, headers_end: int) -> int:
        line_end = buf.find(b"\r\n")

        try:
            req_line = buf[:line_end].split(b" ", 2)
        except ValueError:
            raise MalformedRequestLineError(buf[:line_end])
        
        self.method, self.path, self.proto = req_line
        self.headers = []

        try:
            raw_headers = buf[line_end+2:headers_end].split(b"\r\n")
            for pair in raw_headers:
                k, v = (pair.decode()).split(": ", 1)

                if k == 'Content-Length':
                    self.content_len = int(v)

                self.headers.append((k, v))

        except ValueError:
            raise IncorrectHeadersFormat(buf[line_end+2:headers_end])
        



class FileWrapper:
    def __init__(self, filelike: typing.BinaryIO, chunksize: int = 8192):
        if not hasattr(filelike, 'read'):
            raise ValueError('Argument passed into file_wrapper must be a file-like object')

        self.filelike = filelike
        self.chunk = chunksize
        if hasattr(self.filelike, 'close'):
            self.close = self.filelike.close

        # try using the cool memory map or fall back to regular file reading if we cant
        try:
            self.mm = mmap.mmap(self.filelike.fileno(), 0, access=mmap.ACCESS_READ)
            self.read = 0
        except Exception as e:
            print(str(e))
            self.mm = None

    def __iter__(self):
        return self
    
    def __next__(self):
        if not self.mm:
            data = self.filelike.read(self.chunk)
            if not data:
                raise StopIteration
            return data

        end = min(self.read+self.chunk, len(self.mm))
        data = self.mm[self.read:end]

        if not data:
            self.mm.close()
            raise StopIteration
        self.read += len(data)
        
        return data