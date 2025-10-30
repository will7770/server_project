from server.http.wsgi import Server
from server.config import init_args, init_debug_args
from server.utils import Logger



def run():
    args = init_debug_args()

    logger = Logger('info')
    logger.init_logger()

    server = Server(args.app, args.host, args.port)
    server.run()


if __name__ == '__main__':
    run()