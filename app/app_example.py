from flask import Flask, request
import time


def basic_app(environ, start_response):
    headers = [('X-custom-header', 'its custom!'),
               ('X-powered-by', 'Deouserver')]
    
    status = '200 OK'
    start_response(status, headers)

    return [b"Hello world"]
    


app = Flask(__name__)

@app.route("/get", methods=['GET'])
def get_example():

    return {"Hello,": " world!"}

@app.route("/post", methods=['POST'])
def post_example():
    body = request.get_json()
    print(body['title'], body['desc'])
    r = request.environ()
    return {"environ", r}

@app.route("/long", methods=['GET'])
def long_operation():
    time.sleep(5)
    return {"This took a long time": "..."}