from server.http.wsgi import Server
from server.config import Config
from server.utils import Logger
from server.errors import FatalConfigException, ServerExit
import logging
import sys
import traceback



def run(config: Config = None):
    """Main entry point of the server.

    Args:
        config (Config, optional): Accepts an instance of Config class, must be present when running outside CLI.
    """
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
            
    if cfg.logging_level == 'debug':
        logger.debug("Config options:")
        logger.debug(cfg.list_config_to_str())

    server = Server(cfg)
    try:
        server.run()
    except ServerExit as se:
        if se.__cause__:
            traceback.print_exception(type(se), se, se.__traceback__)
        sys.exit()

  

if __name__ == '__main__':
    run()