import socket
from ..sock import TCPsocket
from .handlers import Request, Response
import logging
import signal
from ..utils import init_signals, Logger
import datetime
import typing
from ..errors import *
from ..config import init_args, init_debug_args
import errno



class Server:
    def __init__(self, app: typing.Callable, host: str = 'localhost', port: int = 8000, backlog: int = 2048):
        self.app: typing.Callable = app
        self.host: str = host
        self.port: int = port
        self.backlog: int = backlog
        self.running: bool = False
        self.server_socket: socket.socket = None
        self.logger = logging.getLogger(__name__)


    def handle_request(self, client: socket.socket, app: typing.Callable, addr: str):
        try:
            request = Request()
            response = Response(client)
            
            try:
                request.build_request(client)
            except (ClientDisconnect, ConnectionResetError):
                client.shutdown(socket.SHUT_RDWR)
                client.close()
                return
        
            environ = request.build_environ()

            app_result = response.handle_app(app, environ)
            # release resources
            if hasattr(app_result, 'close'):
                app_result.close()
        finally:
            client.close()


    def run(self):
        try:
            self.prepare_server()
        except Exception:
            self.logger.fatal("Failed to prepare the server", exc_info=True)

        self.running = True

        self.server_socket = TCPsocket(self.host, self.port, self.backlog).deploy()

        self.logger.info(f'Serving on {self.host}:{self.port}')
        try:
            while self.running:
                try:
                    client, remote_addr = self.server_socket.accept()
                    client.setblocking(0)
                    self.logger.info("Received connection from %s", remote_addr)

                    self.handle_request(client, self.app, remote_addr)
                except OSError as e:
                    if e.errno not in (errno.EAGAIN, errno.ECONNABORTED, errno.EWOULDBLOCK):
                        raise
                    if not self.running:
                        break
                    continue
        finally:
            self.finish()


    def prepare_server(self):
        init_signals([
        (signal.SIGINT, self.sigint_handler)
        ])


    def sigint_handler(self, signum, frame):
        self.logger.info('SIGINT received, finishing the process. . .')
        self.running = False


    def finish(self):
        self.server_socket.close()
        self.logger.info("Process finished.")