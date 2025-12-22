import socket
from .base import BaseWorker
from ..http.handlers import Request, Response
from ..http.errors import *
import typing
from ..errors import *
import errno
import select
from ..sock import SocketReader




class SyncWorker(BaseWorker):
    def run(self):
        self.alive = True

        self.prepare_worker()

        while self.alive:
            ready = self.get_ready()
            if not ready and not self.alive:
                break

            if ready:
                for sock in ready:
                    try:
                        while True: # avoid syscalls by continuously accepting if we can
                            self.accept(sock)
                            continue
                    except OSError as e:
                        if e.errno not in (errno.EAGAIN, errno.ECONNABORTED, errno.EWOULDBLOCK):
                            raise
                        
                if not self.alive:
                    break

        self.close()


    def get_ready(self):
        try:
            ready = select.select(self.listeners, [], [], self.server_sock_timeout)
            return ready[0]
        except OSError as err:
            if err.errno in (errno.EINTR, errno.EBADF):
                return []
    
    
    def handle_connection(self, client: socket.socket, addr: str):
        try:
            request = Request(reader=SocketReader(client))
            self.handle_request(request, client, addr)
        except OSError as e:
            if e.errno not in (errno.EPIPE, errno.ECONNRESET, errno.ENOTCONN, errno.ECONNABORTED):
                self.logger.exception("Socket processing error: %s", str(e))
            elif e.errno == errno.ECONNRESET:
                self.logger.debug('Connection has been reset')
            elif e.errno == errno.ENOTCONN:
                self.logger.debug('Connection does not exist')
            elif e.errno == errno.EPIPE:
                self.logger.debug('Broken pipe')
            elif e.errno == errno.ECONNABORTED:
                self.logger.debug('Connection terminated by client')
        finally:
            client.close()
    
    
    def handle_request(self, request: Request, client: socket.socket, addr: str):
        try:
            response = Response(client, request)
        
            request.build_request()
            request.notify()
            
            # force connection: close on sync worker
            request.keepalive = 0
            
            environ = response.build_environ()

            app_result = response.handle_app(self.app, environ)
            
            # release resources
            if hasattr(app_result, 'close'):
                app_result.close()

        except TimeoutError:
            self.logger.debug("Client %s timed out", addr)
        except (ClientDisconnect, ConnectionResetError):
            self.logger.debug("Client %s disconnected", addr)


    def accept(self, server_sock: socket.socket):
        client_sock, addr = server_sock.accept()
        self.logger.debug("Received connection from %s", addr)
        client_sock.settimeout(self.client_sock_timeout)
        self.handle_connection(client_sock, addr)


    def close(self):
        self.alive = False
        for sock in self.listeners:
            sock.close()