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
        for att in range(3):
            try:
                self.server_sockets = create_sockets(self.bind, self.backlog)
                break
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    self.logger.critical(f"Couldnt bind to adress {self.host}:{self.port}, attempt {att}/3")
                time.sleep(2)

        self.worker = self.worker(app=self.app, listeners=self.server_sockets)
        # log where we listen
        for sock in self.server_sockets:
            address, port = sock.getsockname()
            self.logger.info(f'Serving on http://{address}:{port}')
        try:
            self.worker.run()
        finally:
            self.finish()


    def prepare_server(self):
        pass


    def finish(self):
        self.logger.info("Process finished.")