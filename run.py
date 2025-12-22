from server.http.wsgi import Server
from server.config import Config
from server.utils import Logger
from server.errors import FatalConfigException
import logging



def run(config: Config = None):
    try:
        if not config:
            cfg = Config()
            cfg.init_config()
        else: 
            cfg = config
            cfg.perform_validations()
    except FatalConfigException:
        raise
    
    Logger(cfg.logging_level).init_logger()
    logger = logging.getLogger(__name__)
    
    if cfg._exceptions:
        logger.warning("Some config options werent correct and have been set to defaults:")
        for pair in cfg._exceptions:
            option, exception = pair
            logger.warning(f"Option name: {option}, Exception raised: {exception}\n")

    server = Server(cfg)
    server.run()

  

if __name__ == '__main__':
    run()