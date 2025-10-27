import socket
import io
import sys
from wsgiref.headers import Headers



class Response:
    def __init__(self, sock: socket.socket):
        self.sock: socket.socket = sock
        self.length: int = None
        self.status: str = None
        self.headers_sent: bool = False
        self.headers = []


    def send_headers(self):
        # prepare response
        response = f"HTTP/1.0 {self.status}\r\n"
        headers_list = Headers(self.headers)
        for k, v in headers_list.items():
            response += f"{k}: {v}\r\n"

        response += "\r\n"
        self.sock.sendall(response.encode())
        self.headers_sent = True


    def start_response(self, status: int, response_headers: tuple, exc_info = None) -> callable:
        self.headers = response_headers
        self.status = status

        if not self.headers_sent:
            self.send_headers()

        def write(data):
            if type(data) != bytes:
                try:
                    data = data.encode()
                except AttributeError:
                    print("Cant convert data into bytes")
            self.sock.sendall(data)

        return write



class Request:
    def __init__(self):
        self.body = io.BytesIO()
        self.bufsize = 8192


    def build_request(self, sock: socket.socket) -> bool:
        while True:
            chunk = sock.recv(self.bufsize)
            if chunk == b'':
                # no data, sign that connection is over
                if self.body.getvalue() == b'':
                    return 0
                break
            self.body.write(chunk)
            if len(chunk) < self.bufsize:
                break
        return 1
    
    @property
    def decoded_body(self):
        return self.body.getvalue().decode()
    

    def build_environ(self, request: str) -> dict:
        headers, body = request.split("\r\n\r\n")
        headers = request.split("\r\n")
        general = headers[0]
        method, path, version = general.split(' ')

        split_path = path.split('?')
        if len(split_path) > 2:
            path, query_string = path.split('?', 1)
        else:
            query_string = ''

        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'SERVER_PROTOCOL': version,
            'QUERY_STRING': query_string,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(b""),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }
        # write headers to environ
        for header in headers[1:]:
            if ':' in header:
                name, value = header.split(': ', 1)
                name = name.replace('-', '_')

                if name == 'CONTENT_TYPE' or name == 'CONTENT_LENGTH':
                    environ[name] = value.strip()

                else:
                    name = 'HTTP_' + name
                    environ[name] = value.strip()
        # write body 
        environ['wsgi.input'].write(body.encode())
        self.body.close()

        return environ