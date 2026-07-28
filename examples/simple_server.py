import http.server
import socketserver
import threading
from tunnel_sdk import Tunnel

PORT = 8080

class SimpleHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Hello from Python's Simple HTTP Server!</h1></body></html>")

def run_server():
    with socketserver.TCPServer(("", PORT), SimpleHandler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Start the HTTP server in a background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Initialize the Tunnel SDK (assumes env vars are set, including TUNNEL_LOCAL_URL=http://127.0.0.1:8080)
    print("Starting Tunnel SDK...")
    
    tunnel = Tunnel.from_env()
    
    @tunnel.on("on_connect")
    def on_connect():
        print("Tunnel is connected to the Gateway!")
        
    try:
        # Block the main thread and run the tunnel
        tunnel.run()
    except KeyboardInterrupt:
        print("Shutting down...")
        tunnel.stop()
