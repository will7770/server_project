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
    
    
    def handle_connection(self, server: socket.socket, client: socket.socket, addr: str):
        try:
            request = Request(reader=SocketReader(client), from_addr=client.getsockname(), cfg=self.cfg)
            self.handle_request(server, request, client, addr)
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
        except Exception:
            self.logger.exception("Internal server error has occured")
        finally:
            client.close()
    
    
    def handle_request(self, server: socket.socket, request: Request, client: socket.socket, addr: str):
        try:
            response = Response(sock=client, request=request, cfg=self.cfg)
            app_result = None
            
            request.build_request()
            request.notify()
            
            # force connection: close on sync worker
            response.kill_keepalive = True
    
            environ = response.build_environ(server.getsockname(), self.cfg.mount)

            app_result = self.handle_app(response, self.app, environ)

        except TimeoutError:
            self.logger.debug("Client %s timed out", addr)
        except (ClientDisconnect, ConnectionResetError):
            self.logger.debug("Client %s disconnected", addr)
            
        finally:
            # release resources
            if app_result:
                if hasattr(app_result, 'close'):
                    app_result.close()
            response.close()
            
            
    def handle_app(self, response: Response, app: typing.Callable, environ: dict):
        app_result = app(environ, response.start_response)

        if isinstance(app_result, environ['wsgi.file_wrapper']):
            if not response.write_file(app_result):
                for chunk in app_result: response.write(chunk)

        else:
            for chunk in app_result:
                response.write(chunk)
                
        # some wsgi apps close their resources, return to make it possible
        return app_result


    def accept(self, server_sock: socket.socket):
        client_sock, addr = server_sock.accept()
        self.logger.debug("Received connection from %s", addr)
        
        client_sock.settimeout(self.client_sock_timeout)
        self.handle_connection(server_sock, client_sock, addr)


    def close(self):
        self.alive = False
        for sock in self.listeners:
            sock.close()