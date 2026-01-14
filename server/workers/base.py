import socket
import typing
import signal
from ..utils import init_signals
import logging
import selectors
import sys
from ..config import Config
from abc import ABC, abstractmethod




class BaseWorker(ABC):
    def __init__(self, app: typing.Callable, listeners: list[socket.socket], cfg: Config = Config()):
        self.app = app
        self.listeners = listeners
        self.selector: selectors.BaseSelector = selectors.DefaultSelector
        self.alive = False
        self.logger = logging.getLogger(__name__)
        self.cfg = cfg
        self.server_sock_timeout: int | float = 0.5 # time we make the selector wait for if there are no data in any descriptors
        self.client_sock_timeout: int | float = cfg.client_timeout # how much we let the client sock hang for before closing it
        

    def prepare_worker(self):
        init_signals([
        (signal.SIGINT, self.sigint_handler),
        (signal.SIGTERM, self.sigterm_handler),
        ])


    def sigint_handler(self, signum, frame):
        self.logger.info("Gracefully shutting down the server. . .")
        self.alive = False


    def sigterm_handler(self, signum, frame):
        self.logger.info("Forcefully shutting down the server. . .")
        sys.exit(1)


    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def handle_request(self):
        pass
    
    @abstractmethod
    def handle_connection(self):
        pass
    
    @abstractmethod
    def accept(self):
        pass