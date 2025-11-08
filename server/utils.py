import logging
import importlib.util
import importlib.resources
from pathlib import Path
import signal
import typing
import time



def find_application(path_or_callable: str | typing.Callable) -> typing.Callable:
    if callable(path_or_callable):
        return path_or_callable

    path = path_or_callable
    if not ':' in path:
        raise ValueError("Invalid path format")
    full_path = path.split(':', 1)
    
    path, app = full_path[0], full_path[1]
    if path.endswith('.py'):
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError("No file with such name found")
        
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(path)

    app = getattr(module, app)
    if not callable(app):
        raise TypeError("%s must be a callable object" % app)
    
    return app



def init_signals(pairs: list[tuple[int, typing.Callable]]):
    for pair in pairs:
        signal.signal(pair[0], pair[1])



class Logger:
    levels = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG
    }


    def __init__(self, level: typing.Literal['critical', 'error', 'warning', 'info', 'debug']):
        self.level = level

    def init_logger(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')