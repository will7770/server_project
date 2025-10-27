import argparse
from app.app_example import app
from server.utils import find_application

class Config:
    pass


def init_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=str)
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8000)

    args = parser.parse_args()
    # verify app argument
    if args.debug:
        wsgi_app = app
    else:
        wsgi_app = find_application(args.app)
    args.app = wsgi_app

    return args


def init_debug_args() -> argparse.Namespace:
    return argparse.Namespace(app=app, host='localhost', port=8000)