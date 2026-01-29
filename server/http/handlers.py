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
#import urllib3




# thanks gunicorn
RFC9110_5_6_2_TOKEN_SPECIALS = r"!#$%&'*+-.^_`|~"
RFC9110_5_5_INVALID_AND_DANGEROUS = re.compile(r"[\0\r\n]")
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

        # check the offset and calculate response len. if not set already
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

        # return the pointer to its previous place like nothing happened
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


    def build_environ(self, sockname: tuple[str, str], mount: str) -> dict:
        req = self.request
        split_path = (req.path).split('?')

        if len(split_path) != 2:
            path, query_string = split_path[0], ''
        else:
            path, query_string = split_path

        environ = {
            'SCRIPT_NAME': mount,
            'REQUEST_METHOD': req.method,
            'PATH_INFO': path[len(mount):] if mount else path,
            'SERVER_PROTOCOL': req.version,
            'QUERY_STRING': query_string,
            'REMOTE_ADDR': self.sock.getpeername(),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': BodyWrapper(self.request.reader, self.request.content_len),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.file_wrapper': FileWrapper
        }
        environ['SERVER_NAME'], environ['SERVER_PORT'] = sockname
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
    __slots__ = ('from_addr', 'bufsize', 'content_len', 'host', 'headers', 'method',
                  'path', 'version', 'keepalive', 'logger', 'reader')
    
    MAX_HEADER_AMOUNT = 128
    MAX_REQUEST_LINE = 8192
    MAX_HEADER_SIZE = 32768
    MAX_SINGLE_HEADER = 8192

    def __init__(self, reader: SocketReader, from_addr: str):
        self.from_addr: str = from_addr
        self.bufsize: int = 8192
        self.content_len: int = 0
        self.host: str = None
        self.headers: list[tuple[str, str]] = []
        self.method: str = None
        self.path: str = None
        self.version: str = None
        self.keepalive: int = 1
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.reader: SocketReader = reader
        

    def build_request(self):
        # fill initial buffer with whatever
        self.reader.fill()

        headers_start = self.parse_request_line()

        headers_end = self.parse_headers(headers_start)

    
    def parse_headers(self, headers_start: int) -> int:
        # get headers end index
        while True:
            headers_end = self.reader.find(b'\r\n\r\n')
            if headers_end-headers_start > self.MAX_HEADER_SIZE:
                raise HeaderOverflow("Max headers size limit reached", self.MAX_HEADER_SIZE)
            if headers_end >= 0:
                break
            if self.reader.fill() == 0:
                raise ClientDisconnect
            
        raw_headers = self.reader.read_until(until_index=headers_end, additionally_advance=4)
        if len(raw_headers) < headers_end-self.reader.rptr:
            self.logger.warning('Buffer returned incomplete data for address %s, disconnecting.', str(self.from_addr))
            raise ClientDisconnect
        
        # begin headers parsing
        try:
            if len(raw_headers) > self.MAX_HEADER_SIZE:
                raise HeaderOverflow("Max headers size limit reached", self.MAX_HEADER_SIZE)
            
            raw_headers = [header.decode() for header in raw_headers.split(b"\r\n")]
            if len(raw_headers) > self.MAX_HEADER_AMOUNT:
                raise HeaderOverflow("Max amount of headers reached", self.MAX_HEADER_AMOUNT)
            
            for header in raw_headers:
                if header.find(":") <= 0:
                    raise IncorrectHeader(header)
                if len(header)+2 > self.MAX_SINGLE_HEADER:
                    raise HeaderOverflow("Max size for single header reached", self.MAX_SINGLE_HEADER)
                    
                k, v = header.split(":", 1)

                if k.rstrip(" \t") != k:
                    raise IncorrectHeader(header)
                if not TOKEN_RE.fullmatch(k):
                    raise IncorrectHeader(header)
                
                v = v.strip(" \t")
                if RFC9110_5_5_INVALID_AND_DANGEROUS.search(v):
                    raise IncorrectHeader(header)

                if k == 'Content-Length':
                    if self.content_len:
                        raise DuplicateHeader(k)
                    self.content_len = int(v)
                elif k == 'Host':
                    if self.host:
                        raise DuplicateHeader(k)
                    self.host = v
                elif k == 'Connection':
                    if v == 'close':
                        self.keepalive = 0

                self.headers.append((k, v))
            
            return headers_end
        except (ValueError, UnicodeDecodeError):
            raise IncorrectHeadersFormat(raw_headers)
        
        
    def parse_request_line(self) -> int:
        while True:
            idx = self.reader.find(b'\r\n')
            if idx > self.MAX_REQUEST_LINE:
                raise RequestLineOverflow(self.MAX_REQUEST_LINE)
            
            if idx >= 0:
                req_line = self.reader.read_until(until_index=idx, additionally_advance=2)
                if len(req_line) > self.MAX_REQUEST_LINE:
                    raise RequestLineOverflow(self.MAX_REQUEST_LINE)
                break
            if self.reader.fill() == 0:
                raise ClientDisconnect
            
        if len(req_line) < idx-self.reader.rptr:
            self.logger.warning('Buffer returned incomplete data for address %s, disconnecting.', str(self.from_addr))
            raise ClientDisconnect
        
        try:
            req_line = req_line.decode()
            self.method, self.path, self.version = req_line.split(" ", 2)
            
            # method checks
            if not TOKEN_RE.fullmatch(self.method):
                raise IncorrectMethodError(self.method)
            if not 3 <= len(self.method) < 32:
                raise IncorrectMethodError(self.method)
            
            # path
            if len(self.path) == 0:
                raise MalformedRequestLineError(req_line)
            
            # version
            version_format = re.compile(r"HTTP/(\d).(\d)")
            matched = version_format.fullmatch(self.version)
            if matched is None:
                raise MalformedRequestLineError(req_line)
            
            version = (int(matched.group(1)), int(matched.group(2)))
            if not version <= (1, 1):
                raise UnsupportedOrIncorrectHTTPVersion(self.version)
            
            return idx+2
        except ValueError:
            raise MalformedRequestLineError(req_line)
    
    
    def notify(self):
        self.logger.info("%s %s", self.method, self.path)