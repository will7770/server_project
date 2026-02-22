import socket
import io
import sys
import typing
from .errors import *
from ..errors import *
from datetime import datetime, timezone
import re
from ..utils import reraise, is_hop_by_hop, get_cached_http_date
import os
import logging
from ..sock import SocketReader
from .wrappers import FileWrapper, BodyWrapper, ChunkedBodyWrapper
from typing import Literal
from ..config import Config
from urllib.parse import unquote




# thanks gunicorn
RFC9110_5_6_2_TOKEN_SPECIALS = r"!#$%&'*+-.^_`|~"
RFC9110_5_5_INVALID_AND_DANGEROUS = re.compile(r"[\0\r\n]")

TOKEN_RE = re.compile(r"[%s0-9a-zA-Z]+" % (re.escape(RFC9110_5_6_2_TOKEN_SPECIALS)))
VERSION_FORMAT = re.compile(r"HTTP/(\d).(\d)")
HEADER_VALUE_RE = re.compile(r'[ \t\x21-\x7e\x80-\xff]*')

HOP_BY_HOP_HEADERS = frozenset({"CONNECTION", "KEEP-ALIVE", "PROXY-AUTHENTICATE", "PROXY-AUTHORIZATION", "TE","TRAILERS", "TRANSFER-ENCODING", "UPGRADE"})




class Response:
    __slots__ = ('sock', 'response_length', 'status', 'headers_sent',
                 'headers', 'kill_keepalive', 'sent', 'logger', 'request', 'cfg')

    def __init__(self, sock: socket.socket, request: "Request", cfg: Config):
        self.sock: socket.socket = sock
        self.response_length: int = None
        self.status: str = None
        self.headers_sent: bool = False
        self.headers: list[tuple[str, str]] = []
        self.kill_keepalive: bool = False
        self.sent: int = 0
        self.logger = logging.getLogger(__name__)
        self.request: "Request" = request
        self.cfg: Config = cfg


    @property
    def use_chunked(self) -> bool:
        if self.response_length:
            return False
        elif self.request.method == 'HEAD':
            return False
        elif self.status in (204, 304):
            return False
        return True
        
    
    @property
    def should_keep_alive(self) -> bool:
        if self.kill_keepalive or self.cfg.avoid_keepalive:
            return False 
        elif not self.request.keepalive:
            return False
        elif not (self.use_chunked or self.response_length is not None):
            return False
        return True
        
    
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
                    reraise(exc_info[0], exc_info[1], exc_info[2])
            finally:
                del exc_info
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
        
        # avoid concantenation, instead send chunk header right away
        elif self.use_chunked:
            header = f"{to_send:X}\r\n"
            self.sock.sendall(header.encode())
            
        self.sent += response.nbytes
        self.sock.sendall(response)
        
        if self.use_chunked:
            self.sock.sendall(b"\r\n")
            
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
    

    def process_headers(self, headers: list[tuple[str, str]]):
        for token, val in headers:
            if is_hop_by_hop(token.upper(), HOP_BY_HOP_HEADERS):
                continue
            
            if type(token) != str or not TOKEN_RE.fullmatch(token):
                raise IncorrectHeadersFormat(token)
            
            if type(val) != str or not HEADER_VALUE_RE.fullmatch(val):
                raise IncorrectHeadersFormat(val)

            if token == 'Content-Length':
                self.response_length = int(val)

            self.headers.append((token, val))
        
        # append server headers
        if not self.should_keep_alive:
            self.headers.append(('Connection', 'close'))
        if self.use_chunked:
            self.headers.append(("Transfer-Encoding", "chunked"))
            
        self.headers.append(( "Date", get_cached_http_date().strftime('%a, %d %b %Y %H:%M:%S GMT') ))
        self.headers.append(("Server", self.cfg.servername))


    def build_environ(self, sockname: tuple[str, str], mount: str) -> dict:
        req = self.request
        split_path = (req.path).split('?')

        if len(split_path) != 2:
            path, query_string = split_path[0], ''
        else:
            path, query_string = split_path

        # relative path to mount
        path = path[len(mount):] if mount else path
        
        # TODO: this will require special handling when unix sockets are implemented
        environ = {
            'SCRIPT_NAME': mount,
            'REQUEST_METHOD': req.method,
            'PATH_INFO': unquote(path),
            'SERVER_PROTOCOL': req.version,
            'QUERY_STRING': query_string,
            'REMOTE_ADDR': sockname[0],
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': self.set_body_wrapper(),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.file_wrapper': FileWrapper
        }
        environ['SERVER_NAME'], environ['SERVER_PORT'] = self.sock.getsockname()
        # write headers to environ
        for header_pair in req.headers:
            name, value = header_pair
            name = name.replace('-', '_')

            if name == 'CONTENT_TYPE':
                environ[name.upper()] = value.strip()
            elif name == 'CONTENT_LENGTH':
                # empty content_length if chunked encoding is being received
                environ[name.upper()] = value.strip() if not self.request.chunked_encoding else 0
            else:
                # skip hbh headers
                if is_hop_by_hop(name.upper(), HOP_BY_HOP_HEADERS):
                    continue
                
                name = 'HTTP_' + name
                # concantenate duplicate headers which are allowed to be duplicated
                if name in environ:
                    environ[name] = f"{environ[name]},{value.strip()}"
                else:
                    environ[name] = value.strip()

        return environ
    
    
    def set_body_wrapper(self) -> ChunkedBodyWrapper | BodyWrapper:
        if self.request.content_len and self.request.chunked_encoding:
            # we dont do that here
            raise IncorrectHeader("CONTENT-LENGTH")
        
        if self.request.chunked_encoding:
            return ChunkedBodyWrapper(self.request.reader)
        elif self.request.content_len:
            return BodyWrapper(self.request.reader, self, self.request.content_len)
        else:
            return io.BytesIO()
        
        
    def close(self):
        if not self.headers_sent:
            self.send_headers()
        if self.use_chunked:
            self.sock.sendall(b"0\r\n\r\n")




class Request:
    __slots__ = ('from_addr', 'expects_100_continue', 'content_len', 'host', 'headers', 'method',
                  'path', 'version', 'keepalive', 'logger', 'reader', 'cfg', 'chunked_encoding')
    
    MAX_HEADER_AMOUNT = 128
    MAX_REQUEST_LINE = 8192
    MAX_HEADER_SIZE = 32768
    MAX_SINGLE_HEADER = 8192

    def __init__(self, reader: SocketReader, from_addr: str, cfg: Config):
        self.from_addr: str = from_addr
        self.content_len: int = 0
        self.host: str = None
        self.expects_100_continue: bool = False
        self.headers: list[tuple[str, str]] = []
        self.method: str = None
        self.path: str = None
        self.version: str = None
        self.keepalive: int = 1
        self.chunked_encoding: bool = False
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.cfg: Config = cfg
        self.reader: SocketReader = reader
        

    def build_request(self):
        headers_start = self.parse_request_line()
        headers_end = self.parse_headers(headers_start)

    
    def parse_headers(self, headers_start: int) -> int:
        try:
            headers_end, raw_headers = self._get_headers(headers_start)
            
            if len(raw_headers) > self.MAX_HEADER_SIZE:
                raise HeaderOverflow("Max headers size limit reached", self.MAX_HEADER_SIZE)
            
            raw_headers = [header for header in raw_headers.split("\r\n")]
            if len(raw_headers) > self.MAX_HEADER_AMOUNT:
                raise HeaderOverflow("Max amount of headers reached", self.MAX_HEADER_AMOUNT)
            
            for header in raw_headers:
                if header.find(":") <= 0:
                    raise IncorrectHeader(header)
                if len(header)+2 > self.MAX_SINGLE_HEADER:
                    raise HeaderOverflow("Max size for single header reached", self.MAX_SINGLE_HEADER)
                    
                k, v = header.split(":", 1)

                # normalization
                k = k.upper()
                
                # ignore headers with underscores
                if '_' in k:
                    continue
                
                # header checks
                if k.rstrip(" \t") != k:
                    raise IncorrectHeader(header)
                if not TOKEN_RE.fullmatch(k):
                    raise IncorrectHeader(header)
                
                # header value checks
                v = v.strip(" \t")
                if RFC9110_5_5_INVALID_AND_DANGEROUS.search(v):
                    raise IncorrectHeader(header)

                # TODO: nullify those on every keepalive request
                # duplicate sensitive headers
                if k == 'CONTENT-LENGTH':
                    if self.content_len:
                        raise DuplicateHeader(k)
                    self.content_len = int(v)
                    
                elif k == 'HOST':
                    if self.host:
                        raise DuplicateHeader(k)
                    self.host = v
                
                # special
                elif k == 'CONNECTION':
                    if v == 'close':
                        self.keepalive = 0
                
                elif k == 'EXPECT':
                    if v != '100-continue':
                        raise ExpectationFailed(v)
                    self.expects_100_continue = True
                
                elif k == 'TRANSFER-ENCODING':
                    if self.chunked_encoding:
                        raise DuplicateHeader(k)
                    encodings = v.split(',')
                    # if theres more than 1 encoding or the encoding isnt chunked, assume we cant do anything for the request
                    if len(encodings) > 1 or encodings[0] != 'chunked':
                        raise UnsupportedEncoding(encodings)
                    self.chunked_encoding = True

                self.headers.append((k, v))
            
            # required for http 1.1
            if not self.host:
                raise MissingRequiredHeader('Host')
            
            return headers_end
        
        except (ValueError, UnicodeDecodeError):
            raise IncorrectHeadersFormat(raw_headers)
        
        
    def parse_request_line(self) -> int:  
        try:
            headers_start_idx, req_line = self._get_request_line()
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
            version_match = VERSION_FORMAT.fullmatch(self.version)
            if version_match is None:
                raise MalformedRequestLineError(req_line)
            
            version = (int(version_match.group(1)), int(version_match.group(2)))
            if not version <= (1, 1):
                raise UnsupportedOrIncorrectHTTPVersion(self.version)
            
            return headers_start_idx+2
        except ValueError:
            raise MalformedRequestLineError(req_line)
    
    
    def _get_request_line(self) -> tuple[int, str]:
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
        
        return idx, req_line.decode()
    
    
    def _get_headers(self, headers_start: int) -> tuple[int, str]:
        while True:
            headers_end = self.reader.find(b'\r\n\r\n')
            if headers_end-headers_start > self.MAX_HEADER_SIZE:
                raise HeaderOverflow("Max headers size limit reached", self.MAX_HEADER_SIZE)
            if headers_end >= 0:
                break
            if self.reader.fill() == 0:
                raise ClientDisconnect
        
        try:
            raw_headers = self.reader.read_until(until_index=headers_end, additionally_advance=4)
        except IncompleteBufferResponse:
            self.logger.warning('Buffer returned incomplete data for address %s, disconnecting.', str(self.from_addr))
            raise ClientDisconnect

        return headers_end, raw_headers.decode()
    
    
    def notify(self):
        self.logger.info("%s %s", self.method, self.path)