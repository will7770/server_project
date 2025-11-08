import argparse
from app.app_example import app
from server.utils import find_application
from .errors import FatalConfigException
import typing
import importlib




class Config:
    def __init__(self):
        # server config options
        self.app: typing.Callable = None
        self.bind: list[tuple[str, int]] = []
        self.backlog: int = 2048
        self.workertype: typing.Literal['sync'] = 'sync'

        # misc
        self.exceptions: list[tuple[str, str]] = []


    def perform_validations(self):
        self.verify_app(self.app)
        self.verify_worker(self.workertype)
        self.verify_bind_addresses(self.bind) # first it accepts raw addresses passed by argparse, like 127.0.0.1:8000, only then assigns tuples to self.bind


    def verify_worker(self, worker_class: str):
        WORKERS_MAP = {
           'sync': 'server.workers.sync.SyncWorker',
        }
        if worker_class not in WORKERS_MAP:
            self.exceptions.append(('workertype', "Incorrect worker_class name, using sync worker instead."))
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
                self.exceptions.append(('bind', f'Couldnt resolve the address {addr}')) 
        self.bind = _bind



def init_config(debug: bool = False) -> Config:
    if debug:
        cfg = Config()
        setattr(cfg, 'app', 'app/app_example.py:app')
        setattr(cfg, 'bind', ['127.0.0.1:8000'])
        cfg.perform_validations()
        return cfg

    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=str)
    parser.add_argument('--bind', type=str, default=['127.0.0.1:8000'], nargs='+')
    parser.add_argument('--workertype', type=str, default='sync')

    args = parser.parse_args()
    config = Config()

    for k, v in vars(args).items():
        setattr(config, k, v)

    config.perform_validations()
    
    return config