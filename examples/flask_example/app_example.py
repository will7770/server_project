from flask import Flask, request, jsonify, Response, render_template, send_file
import time
import os
from server import Config, run
    


app = Flask(__name__, template_folder='examples/flask_example/templates', static_folder='examples/flask_example/static')
app.debug = True



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
    title = request.form['title']
    desc = request.form['desc']
    return jsonify({'title': title, 'desc': desc})


@app.route("/receive_stream", methods=['POST'])
def stream():
    # bad example of my ChunkedBodyWrapper getting used.
    full_data = b""
    while True:
        chunk = request.environ['wsgi.input'].read(1024)
        if not chunk:
            break
        full_data += chunk

    return {
        "received": str(full_data),
    }


@app.route("/stream", methods=['GET'])
def transmit_stream():
    def generate_chunks():
        with open(app.static_folder+'/image.jpg', 'rb') as fd:
            while chunk := fd.read(1024*16):
                yield chunk
                
    return Response(generate_chunks(), mimetype='application/octet-stream')


@app.route("/long", methods=['GET'])
def long_operation():
    time.sleep(5)
    return {"This took a long time": "..."}


@app.route("/index", methods=['GET'])
def test_template():
    return render_template('index.html')


@app.route('/get_file', methods=['GET'])
def test_files():
    path = os.path.join(app.template_folder, 'index.html')
    return send_file(path)


@app.route('/get_image', methods=['GET'])
def test_image():
    path = os.path.join(app.static_folder, 'image.jpg')
    return send_file(path)


# Example of running the server outside CLI
# cfg = Config(app=app, logging_level='debug')
# run(config=cfg)