import socket
from .base import BaseWorker
from ..http.handlers import Request, Response
from ..http.errors import *
import typing
from ..errors import *
import errno
import selectors




class SyncWorker(BaseWorker):
    def run(self):
        self.alive = True
        self.selector = selectors.DefaultSelector()
        selector = self.selector # shortcut

        self.prepare_worker()
        # register listeners
        for listener in self.listeners:
            selector.register(listener, selectors.EVENT_READ)

        try:
            while self.alive:
                events = selector.select(self.server_sock_timeout)

                for key, mask in events:
                    if key.data is None:
                        try:
                            self.accept(key.fileobj)
                        except OSError as e:
                            if e.errno not in (errno.EAGAIN, errno.ECONNABORTED, errno.EWOULDBLOCK):
                                raise
                            
                    if not self.alive:
                        break
        finally:
            self.close()


    def handle_request(self, client: socket.socket, addr: str):
        try:
            request = Request()
            response = Response(client)
        
            request.build_request(client)
        
            environ = response.build_environ(request)

            app_result = response.handle_app(self.app, environ)
            # release resources
            if hasattr(app_result, 'close'):
                app_result.close()

        except TimeoutError:
            self.logger.debug("Client %s timed out", addr)
        except (ClientDisconnect, ConnectionResetError):
            self.logger.debug("Client %s disconnected / reset", addr)

        finally:
            client.shutdown(socket.SHUT_RDWR)
            client.close()


    def accept(self, server_sock: socket.socket):
        client_sock, addr = server_sock.accept()
        self.logger.info("Received connection from %s", addr)
        client_sock.settimeout(self.client_sock_timeout)
        self.handle_request(client_sock, addr)


    def close(self):
        self.alive = False
        for sock in self.listeners:
            self.selector.unregister(sock)
        self.selector.close()
        self.close_sockets()


    def close_sockets(self):
        for sock in self.listeners:
            sock.close()