from server.http.wsgi import Server
from server.config import init_config
from server.utils import Logger
from server.errors import FatalConfigException
import logging



def run():
    logger = Logger('info')
    logger.init_logger()

    runner_logger = logging.Logger(__name__)

    try:
        cfg = init_config(debug=True)
    except FatalConfigException:
        runner_logger.fatal("Some important config options werent set/were set incorrectly", exc_info=True)
        return
    
    if cfg.exceptions:
        print("Some config options werent correct and have been set to defaults:")
        for pair in cfg.exceptions:
            option, exception = pair
            print(f"Option name: {option}, Exception raised: {exception}\n")

    server = Server(cfg)
    server.run()


if __name__ == '__main__':
    run()