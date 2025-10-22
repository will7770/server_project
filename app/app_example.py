def basic_app(environ, start_response):
    headers = [('X-custom-header', 'its custom!'),
               ('X-powered-by', 'Deouserver')]
    
    status = '200 OK'
    start_response(status, headers)

    return [b"Hello world"]
    