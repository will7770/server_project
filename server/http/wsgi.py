import socket
from ..sock import TCPsocket
from wsgiref.headers import Headers
import sys
import io


class Server:
    def __init__(self):
        self.host: str = '127.0.0.1'
        self.port: int = 8000
        self.backlog: int = 1024
        self.running: bool = False
        self.server_socket: socket.socket = None


    def handle_request(self, client: socket.socket, app):
        with client:
            request = Request()
            response = Response(client)

            request.build_request(client)

            readable_request = request.decoded_body
            environ = request.build_environ(readable_request)

            app_result = app(environ, response.start_response)
            for item in app_result:
                client.sendall(item)

            # release resources
            if hasattr(app_result, 'close'):
                app_result.close()


    def run(self, app: callable, host: str, port: int):
        self.host, self.port = host, port
        self.running = True
        self.server_socket = TCPsocket('127.0.0.1', 8000, self.backlog).deploy()

        print(f"Listening on {host}:{port}")
        try:
            while self.running:
                client, remote_addr = self.server_socket.accept()

                print(f"Received connection from {remote_addr}")

                self.handle_request(client, app)
        except KeyboardInterrupt:
            print("Shutting down")
        finally:
            self.finish()


    def finish(self):
        self.running = False
        self.server_socket.close()



class Response:
    def __init__(self, sock):
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


    def start_response(self, status, response_headers, exc_info = None):
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
        self.bufsize = 4096


    def build_request(self, sock: socket.socket):
        receiving_body = False
        while True:
            chunk = sock.recv(self.bufsize)
            if not chunk:
                break
            self.body.write(chunk)
            if b'\r\n\r\n' in chunk and not receiving_body:
                receiving_body = True
            if b'\r\n\r\n' in chunk and receiving_body:
                break

    
    @property
    def decoded_body(self):
        return self.body.getvalue().decode()
    

    def build_environ(self, request: str):
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