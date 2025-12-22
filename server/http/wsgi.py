import socket
from ..sock import TCPsocket, BaseSocket, create_sockets
import logging
import signal
from ..workers.base import BaseWorker
from ..utils import init_signals, Logger
import datetime
import typing
from ..errors import *
import errno
import time
import selectors
from ..config import Config
import sys



class Server:
    def __init__(self, cfg: Config):
        self.cfg = cfg

        self.app: typing.Callable = cfg.app
        self.bind: list[tuple[str, str]] = cfg.bind
        self.backlog: int = cfg.backlog
        self.server_sockets: list[socket.socket] = None
        self.worker: BaseWorker = cfg.workertype

        self.logger = logging.getLogger(__name__)


    def run(self):
        try:
            self.prepare_server()
        except Exception:
            self.logger.fatal("Failed to prepare the server", exc_info=True)
            return

        # deploy sockets, retry up to 3 times with a timeout
        for att in range(1, 4):
            try:
                self.server_sockets = create_sockets(self.bind, self.backlog)
                break
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    self.logger.critical("Address %s:%s is in use, retrying. (Аttempt %i/3)", self.host, self.port, att)
                elif e.errno == errno.EADDRNOTAVAIL:
                    self.logger.critical("Address %s:%s is not available, retrying. (Аttempt %i/3)", self.host, self.port, att)
                elif e.errno == errno.EACCES:
                    self.logger.critical("No permission to open a socket at address %s:%s, retrying. (Аttempt %i/3)", self.host, self.port, att)
                else:
                    self.logger.critical("Unexpected OS error occured while starting socket at address %s:%s, retrying. (Аttempt %i/3) (Error: %s)", self.host, self.port, att, str(e))
                time.sleep(2)
            except Exception as e:
                self.logger.critical("Unexpected error occured while trying to init sockets: %s (Аttempt %i/3)", str(e), att)
                time.sleep(2)
        else:
            self.logger.critical("Sockets failed to deploy, finishing the process. . .")
            self.finish(True)

        self.worker = self.worker(app=self.app, listeners=self.server_sockets, cfg=self.cfg)
        # log where we listen
        for sock in self.server_sockets:
            address, port = sock.getsockname()
            self.logger.info(f'Serving on http://{address}:{port}')
        self.worker.run()
        try:
            self.worker.run()
        finally:
            self.finish()


    def prepare_server(self):
        pass


    def finish(self, failure: bool = False):
        if not failure:
            self.logger.info("Process finished.")
            sys.exit(0)
        self.logger.info("Process finished due to an error.")
        sys.exit(1)