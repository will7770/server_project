import argparse
from server.utils import find_application
from .errors import FatalConfigException
import typing
import importlib




class Config:
    """
    Configuration class for WSGI server settings.
    

    Attributes:
        app (typing.Callable): The WSGI application callable that will handle requests.
        
        
        bind (list[tuple[str, int]]): List of (host, port) tuples to bind the server to.
            Currently only supports TCP.
            
            Default: ('127.0.0.1', 8000)
        
        
        backlog (int): Maximum number of pending connections in the socket's listen queue.
        
            Default: 2048
        
        
        workertype (typing.Literal['sync']): The type of worker processing model to use.
            Options:
            'sync' - Synchronous worker, processes one request at a time
            
            Default: 'sync'
            
            
        logging_level (typing.Literal['critical', 'error', 'warning', 'info', 'debug']): Level of logging the logger will use.
        Matches the default python logging levels.
        
            Default: 'info'
            
            
        avoid_keepalive (bool): Avoid keeping the socket connection alive. (sync workers ignore this)
        
            Default: False
            
            
        client_timeout (int): How much time we give the client before closing the connection.
        
            Default: 5
    
            
    Examples:
        Basic config from your code:
        
        >>> config = Config()
        >>> config.app = my_wsgi_app
        >>> config.bind = [('0.0.0.0', 8000)]
        >>> config.backlog = 1024

    
    See Also:
        WSGI Specification: PEP 3333
    """

    def __init__(self):
        # server config options
        self.app: typing.Callable = None
        self.bind: list[tuple[str, int]] = []
        self.backlog: int = 2048
        self.workertype: typing.Literal['sync'] = 'sync'
        self.logging_level: typing.Literal['critical', 'error', 'warning', 'info', 'debug'] = 'info'

        # worker specific
        self.client_timeout: int = 5
        self.avoid_keepalive: bool = False
        
        # internal
        self._exceptions: list[tuple[str, str]] = []


    def perform_validations(self):
        self.verify_app(self.app)
        self.verify_worker(self.workertype)
        self.verify_bind_addresses(self.bind) # first it accepts raw addresses passed by argparse, like 127.0.0.1:8000, only then assigns tuples to self.bind


    def verify_worker(self, worker_class: str):
        WORKERS_MAP = {
           'sync': 'server.workers.sync.SyncWorker',
        }
        if worker_class not in WORKERS_MAP:
            self._exceptions.append(('workertype', "Incorrect workertype name, using sync worker instead."))
            self.workertype = WORKERS_MAP['sync']
        else:
            self.workertype = WORKERS_MAP[worker_class]

        module_path, name = self.workertype.rsplit('.', 1)
        module = importlib.import_module(module_path)
        worker_instance = getattr(module, name)

        self.workertype = worker_instance


    def verify_app(self, path: str):
        try:
            self.app = find_application(path)
        except Exception as e:
            raise FatalConfigException(str(e))
        

    def verify_bind_addresses(self, bind_to: list[str]):
        _bind = []
        for addr in bind_to:
            try:
                host, port = addr.split(':')
                _bind.append((host, int(port)))
            except ValueError:
                self._exceptions.append(('bind', f'Couldnt resolve the address {addr}')) 
        self.bind = _bind



    def init_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('app', type=str)
        parser.add_argument('--bind', type=str, default=['127.0.0.1:8000'], nargs='+')
        parser.add_argument('--workertype', type=str, default='sync')
        parser.add_argument('--avoid_keepalive', action='store_false')
        parser.add_argument('--logging_level', type=str, choices=['critical', 'error', 'warning', 'info', 'debug'], default='info')

        args = parser.parse_args()

        for k, v in vars(args).items():
            setattr(self, k, v)

        self.perform_validations()

        return self