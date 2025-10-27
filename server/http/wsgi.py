import socket
from ..sock import TCPsocket
from .handlers import Request, Response
import logging
from ..config import init_args
import signal
from ..utils import init_signals


class Server:
    def __init__(self, app: callable, host: str = 'localhost', port: int = 8000, backlog: int = 2048):
        self.app = app
        self.host = host
        self.port = port
        self.backlog = backlog
        self.atout = 1 # socket.accept timeout
        self.htout = 1 # handle_request timeout
        self.running: bool = False
        self.server_socket: socket.socket = None
        self.logger = logging.getLogger(__name__)


    def handle_request(self, client: socket.socket, app):
        with client:
            request = Request()
            response = Response(client)

            built = request.build_request(client)
            if not built:
                # client disconnected
                client.shutdown(socket.SHUT_RDWR)
                client.close()
                return

            readable_request = request.decoded_body
            environ = request.build_environ(readable_request)

            app_result = app(environ, response.start_response)
            app_result = b''.join(app_result)
            client.sendall(app_result)

            # release resources
            if hasattr(app_result, 'close'):
                app_result.close()
            client.shutdown(socket.SHUT_RDWR)


    def run(self):
        self.running = True
        init_signals([
            (signal.SIGINT, self.sigint_handler)
        ])
        self.server_socket = TCPsocket(self.host, self.port, self.backlog).deploy()
        self.server_socket.settimeout(self.atout)
        self.logger.info(f'Serving on {self.host}:{self.port}')
        try:
            while self.running:
                try:
                    client, remote_addr = self.server_socket.accept()
                    client.settimeout(self.htout)
                    self.logger.info("Received connection from %s", remote_addr)

                    self.handle_request(client, self.app)
                except socket.timeout:
                    if not self.running:
                        break
                    continue
        finally:
            self.finish()


    def sigint_handler(self, signum, frame):
        self.logger.info('SIGINT received, finishing the process. . .')
        self.running = False


    def finish(self):
        self.server_socket.close()