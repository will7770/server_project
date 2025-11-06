import socket
import io
import sys
from wsgiref.headers import Headers
import typing
from .errors import *
from ..errors import *
import datetime



class Response:
    def __init__(self, sock: socket.socket):
        self.sock: socket.socket = sock
        self.length: int = None
        self.status: str = None
        self.headers_sent: bool = False
        self.headers = []   


    def send_headers(self):
        # prepare response
        response = f"HTTP/1.1 {self.status}\r\n"
        for pair in self.headers:
            k, v = pair
            response += f"{k}: {v}\r\n"

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
        self.headers = response_headers
        self.send_headers()

        def write(data):
            if type(data) != bytes:
                try:
                    data = data.encode()
                except AttributeError:
                    raise IncorrectWriteInvocation
            self.sock.sendall(data)

        return write
    

    def handle_app(self, app: typing.Callable, environ: dict):
        app_result = app(environ, self.start_response)
        for chunk in app_result:
            self.sock.sendall(chunk)
        # some wsgi apps close their resources, return to make it possible
        return app_result



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


    def build_environ(self) -> dict:
        split_path = (self.path.decode()).split('?')

        if len(split_path) != 2:
            path, query_string = split_path[0], ''
        else:
            path, query_string = split_path

        environ = {
            'REQUEST_METHOD': self.method.decode(),
            'PATH_INFO': path,
            'SERVER_PROTOCOL': self.proto.decode(),
            'QUERY_STRING': query_string,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }
        # write headers to environ
        for header_pair in self.headers:
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