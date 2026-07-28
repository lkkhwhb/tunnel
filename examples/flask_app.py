import os
from flask import Flask, jsonify
from tunnel_sdk import Tunnel

app = Flask(__name__)

@app.route("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask through the Tunnel Gateway!"})

if __name__ == "__main__":
    # Ensure these environment variables are set before running:
    # TUNNEL_GATEWAY="wss://gateway.example.com"
    # TUNNEL_API_KEY="your-secret-key"
    # TUNNEL_TARGET_PATH="/api"
    # TUNNEL_LOCAL_URL="http://127.0.0.1:5000"
    
    print("Starting Tunnel...")
    
    # You can either provide parameters directly to Tunnel(...) 
    # or use Tunnel.from_env() to load from environment variables.
    tunnel = Tunnel.from_env()
    
    # Optional callbacks for monitoring connection state
    @tunnel.on("on_connect")
    def on_connect():
        print("Tunnel connected successfully!")
        
    @tunnel.on("on_disconnect")
    def on_disconnect():
        print("Tunnel disconnected. Reconnecting...")
    
    # Start the tunnel in the background
    # Since from_env() loads TUNNEL_LOCAL_URL, we don't need to pass it here.
    tunnel.start()
    
    try:
        # Run the Flask app on the main thread
        print("Starting Flask app on port 5000...")
        app.run(port=5000)
    finally:
        # Ensure graceful shutdown of the tunnel when Flask exits
        print("Shutting down Tunnel...")
        tunnel.stop()
