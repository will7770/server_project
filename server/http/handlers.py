import socket
import io
import sys
import typing
from .errors import *
from ..errors import *
import datetime
import re
import mmap
import os
import logging
from ..sock import SocketReader
from .wrappers import FileWrapper, BodyWrapper




# thanks gunicorn
RFC9110_5_6_2_TOKEN_SPECIALS = r"!#$%&'*+-.^_`|~"
TOKEN_RE = re.compile(r"[%s0-9a-zA-Z]+" % (re.escape(RFC9110_5_6_2_TOKEN_SPECIALS)))

HEADER_VALUE_RE = re.compile(r'[ \t\x21-\x7e\x80-\xff]*')


class Response:
    __slots__ = ('sock', 'response_length', 'status', 'headers_sent',
                 'headers', 'sent', 'body', 'logger', 'request')

    def __init__(self, sock: socket.socket, request: "Request"):
        self.sock: socket.socket = sock
        self.response_length: int = None
        self.status: str = None
        self.headers_sent: bool = False
        self.headers: list[tuple[str, str]] = []
        self.sent: int = 0
        self.body: bytearray = None
        self.logger = logging.getLogger(__name__)
        self.request: "Request" = request


    def send_headers(self):
        # prepare response
        if self.headers_sent:
            return
        
        response = f"HTTP/1.1 {self.status}\r\n" + "\r\n".join([f"{name}: {val}" for name, val in self.headers]) + "\r\n\r\n"
        response = response.encode()

        self.sock.sendall(response)
        self.headers_sent = True


    def start_response(self, status: str, response_headers: list[tuple[str, str]], exc_info = None) -> typing.Callable:
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
        return self.write


    def write(self, data: bytes):
        self.send_headers()

        if not isinstance(data, bytes):
            try:
                data = data.encode()
            except AttributeError:
                raise IncorrectWriteArgument
        
        response = memoryview(data)
        to_send = response.nbytes
        
        if self.response_length:
            if self.response_length <= self.sent:
                return
            to_send = min(self.response_length-self.sent, to_send)
            response = response[:to_send]

        self.sent += response.nbytes
        self.sock.sendall(response)
        response.release()


    def write_file(self, file_wrapper: FileWrapper):
        if not hasattr(file_wrapper.filelike, 'fileno'):
            return False
        
        fileno = file_wrapper.filelike.fileno()

        try:
            offset = os.lseek(fileno, 0, os.SEEK_CUR)
            if not self.response_length:
                size = os.fstat(fileno).st_size
                self.response_length = size - offset
        except (OSError, io.UnsupportedOperation):
            return False
        
        self.send_headers()

        if self.response_length > 0:
            self.sock.sendfile(file_wrapper.filelike, offset, self.response_length)

        os.lseek(fileno, offset, os.SEEK_SET)

        return True


    def handle_app(self, app: typing.Callable, environ: dict):
        app_result = app(environ, self.start_response)

        if isinstance(app_result, FileWrapper):
            if not self.write_file(app_result):
                for chunk in app_result: self.write(chunk)

        else:
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
        
        if not self.request.keepalive:
            self.headers.append(('Connection', 'close'))    


    def build_environ(self) -> dict:
        req = self.request
        split_path = (req.path.decode()).split('?')

        if len(split_path) != 2:
            path, query_string = split_path[0], ''
        else:
            path, query_string = split_path

        environ = {
            'REQUEST_METHOD': req.method.decode(),
            'PATH_INFO': path,
            'SERVER_PROTOCOL': req.version.decode(),
            'QUERY_STRING': query_string,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': BodyWrapper(self.request.reader, self.request.content_len),
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

        return environ




class Request:
    __slots__ = ('bufsize', 'content_len', 'headers', 'method',
                  'path', 'version', 'keepalive', 'logger', 'reader')
    
    MAX_REQUEST_LINE = 8192
    MAX_HEADER_SIZE = 32768

    def __init__(self, reader: SocketReader):
        self.bufsize: int = 8192
        self.content_len: int = 0
        self.headers: list[tuple[str, str]] = []
        self.method: bytes = None
        self.path: bytes = None
        self.version: bytes = None
        self.keepalive: int = 1
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.reader: "SocketReader" = reader
        

    def build_request(self):
        # begin reading request line and headers
        buf = bytearray()
        self.read_into(buf)

        headers_start = self.parse_request_line(buf)
        
        headers_end = buf.find(b"\r\n\r\n")
        while headers_end == -1:
            self.read_into(buf)
            headers_end = buf.find(b"\r\n\r\n")
            if headers_end != -1:
                break

        self.parse_headers(buf, headers_start, headers_end)
        self.reader.put_back(buf, start=headers_end+4)

    
    def parse_headers(self, buf: bytearray, headers_start: int, headers_end: int) -> int:
        try:
            raw_headers = buf[headers_start:headers_end]
            
            if len(raw_headers) > self.MAX_HEADER_SIZE:
                raise HeaderOverflow(self.MAX_HEADER_SIZE)
            
            raw_headers = raw_headers.split(b"\r\n")
            for pair in raw_headers:
                k, v = (pair.decode()).split(": ", 1)

                if k == 'Content-Length':
                    self.content_len = int(v)
                elif k == 'Connection':
                    if v == 'close':
                        self.keepalive = 0

                self.headers.append((k, v))

        except ValueError:
            raise IncorrectHeadersFormat(raw_headers)
        
        
    def parse_request_line(self, data: bytearray) -> int:
        idx = data.find(b"\r\n")
        try:
            req_line = data[:idx]
            
            if len(req_line) > self.MAX_REQUEST_LINE:
                raise RequestLineOverflow(self.MAX_REQUEST_LINE)
            
            self.method, self.path, self.version = req_line.split(b" ", 2)
            return idx+2
        except ValueError:
            raise MalformedRequestLineError(req_line)
        
        
    def read_into(self, buf: bytearray, amount: int = -1):
        data = self.reader.read(amount)
        if len(data) == 0:
            raise ClientDisconnect
        buf.extend(data)
    
    
    def notify(self):
        self.logger.info("%s %s", self.method.decode(), self.path.decode())