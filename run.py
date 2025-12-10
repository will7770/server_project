from server.http.wsgi import Server
from server.config import Config
from server.utils import Logger
from server.errors import FatalConfigException
import logging



def run(config: Config = None):
    logger = Logger('debug')
    logger.init_logger()

    runner_logger = logging.Logger(__name__)

    try:
        if not config:
            cfg = Config()
            cfg.init_config(debug=False)
        else: 
            cfg = config
            cfg.perform_validations()
    except FatalConfigException:
        raise
        # runner_logger.fatal("Some important config options werent set/were set incorrectly", exc_info=True)
        # return
    
    if cfg._exceptions:
        print("Some config options werent correct and have been set to defaults:")
        for pair in cfg._exceptions:
            option, exception = pair
            print(f"Option name: {option}, Exception raised: {exception}\n")

    server = Server(cfg)
    server.run()

  

if __name__ == '__main__':
    run()