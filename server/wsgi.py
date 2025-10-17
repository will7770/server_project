import socket
from .sock import BaseSocket
from wsgiref.headers import Headers
import sys
import io


class Server:
    def __init__(self):
        self.host = None
        self.port = None
        self.backlog = 10


    def handle_request(self, client: socket.socket, app):
        with client:
            request = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                request += chunk
                if b'\r\n\r\n' in chunk:
                    break

            request = request.decode()
            environ = self.parse_request(request)

            headers = []
            body = io.BytesIO()


            def start_response(status, response_headers, exc_info = None):
                headers[:] = [status, response_headers]

                # def write(data):
                #     if type(data) != bytes:
                #         try:
                #             data = data.encode()
                #         except AttributeError:
                #             print("Cant convert data into bytes")
                #     body.write(data)

                # return write


            result = app(environ, start_response)
            for chunk in result: body.write(chunk)

            status, headers_list = headers
            # prepare response
            response = f"HTTP/1.1 {status}\r\n"
            headers_list = Headers(headers_list)
            for k, v in headers_list.items():
                response += f"{k}: {v}\r\n"
            # delete this shit later
            response += "Transfer-Encoding: chunked\r\n"

            response += "\r\n"
            client.sendall(response.encode())
            print(response)

            print(body)
            
            # send body
            body.seek(0)
            client.sendall(body.getvalue())

            body.close()


    def parse_request(self, request):
        separated_request = request.split("\r\n")
        general = separated_request[0]
        print("GENERAL HEADERS", general)
        method, path, version = general.split(' ')

        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'SERVER_PROTOCOL': version,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(b""),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }

        for header in separated_request[1:]:
            if ':' in header:
                name, value = header.split(': ', 1)
                name = name.replace('-', '_')
                if name not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                    name = 'HTTP_' + name
                environ[name] = value.strip()

        return environ


    def run(self, app: callable, host: str, port: int, backlog: int = 1):
        self.host, self.port, self.backlog = host, port, backlog
        with BaseSocket(socket.AF_INET, socket.SOCK_STREAM, self.host, self.port, self.backlog) as sock:
            print(f"Listening on {host}:{port}")
            while True:
                client, remote_addr = sock.accept()
                print(f"Received connection from {remote_addr}")
                self.handle_request(client, app)