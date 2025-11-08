import socket
import typing
import signal
from ..utils import init_signals
import logging
import selectors




class BaseWorker:
    def __init__(self, app: typing.Callable, listeners: list[socket.socket]):
        self.app = app
        self.listeners = listeners
        self.selector: selectors.BaseSelector = selectors.DefaultSelector
        self.alive = False
        self.logger = logging.getLogger(__name__)
        self.server_sock_timeout: int | float = 0.5 # time we make the selector wait for if there are no data in any descriptors
        self.client_sock_timeout: int | float = 15 # how much we let the client sock hang for before closing it


    def prepare_worker(self):
        init_signals([
        (signal.SIGINT, self.sigint_handler)
        ])


    def sigint_handler(self, signum, frame):
        self.logger.info("SIGINT received, shutting down")
        self.alive = False


    def close(self):
        raise NotImplementedError()


    def run(self):
        raise NotImplementedError()


    def handle_request(self):
        raise NotImplementedError()
    

    def accept(self):
        raise NotImplementedError()