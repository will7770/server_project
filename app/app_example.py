from flask import Flask, request, jsonify, Response
import time


def basic_app(environ, start_response):
    headers = [('X-custom-header', 'its custom!'),
               ('X-powered-by', 'Deouserver')]
    
    status = '200 OK'
    start_response(status, headers)

    return [b"Hello world"]
    


app = Flask(__name__)


@app.route("/get/<data>", methods=['GET'])
def get_example(data):
    return jsonify({"Hello,": f"{data}"})


@app.route("/getparams/", methods=['GET'])
def get_with_params():
    return jsonify(request.args)


@app.route("/set_cookie", methods=['GET'])
def test_set_cookie():
    response = jsonify({"Here, ": "have a cookie"})
    response.set_cookie("im_a__cookie", ":)", 500)
    return response


@app.route("/raise_error", methods=['GET'])
def test_raising_error():
    raise ZeroDivisionError("This should get raised")


@app.route("/post", methods=['POST'])
def post_example():
    body = request.get_json()
    print(body['title'], body['desc'])
    r = request.environ
    print(r)
    return {'status': 'sent'}


@app.route("/long", methods=['GET'])
def long_operation():
    time.sleep(5)
    return {"This took a long time": "..."}