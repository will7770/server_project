from flask import Flask, request, jsonify, Response, render_template, send_file
import time
import os




def basic_app(environ, start_response):
    headers = [('X-custom-header', 'its custom!'),
               ('X-powered-by', 'Deouserver')]
    
    status = '200 OK'
    start_response(status, headers)

    return [b"Hello world"]
    


app = Flask(__name__, template_folder='app/templates')



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


@app.route("/long", methods=['GET'])
def long_operation():
    time.sleep(5)
    return {"This took a long time": "..."}


@app.route("/index", methods=['GET'])
def test_template():
    return render_template('index.html')


@app.route('/get_file', methods=['GET'])
def test_files():
    path = os.path.join(app.root_path, 'app/templates/index.html')
    return send_file(path)


@app.route('/get_image', methods=['GET'])
def test_image():
    path = os.path.join(app.root_path, 'app/static/image.jpg')
    return send_file(path)