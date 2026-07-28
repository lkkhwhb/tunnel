"""
Example showing how to run the Tunnel SDK alongside a standard Django deployment.
You can run the SDK as a custom management command, or in a separate script alongside `runserver`.
Here we demonstrate a standalone script that runs alongside your Django server.
"""
import time
from tunnel_sdk import Tunnel

def run_tunnel():
    print("Starting Tunnel SDK for Django...")
    # Assumes your Django app is running on port 8000
    # Make sure TUNNEL_LOCAL_URL is set to http://127.0.0.1:8000
    
    with Tunnel.from_env() as tunnel:
        @tunnel.on("on_connect")
        def connected():
            print("Successfully connected to the Tunnel Gateway!")
            
        @tunnel.on("on_request_start")
        def req_start(req_id):
            print(f"Proxying request {req_id} to Django...")
            
        try:
            print("Press Ctrl+C to stop the tunnel.")
            tunnel.wait()
        except KeyboardInterrupt:
            print("Stopping...")

if __name__ == "__main__":
    run_tunnel()
