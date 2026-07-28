from tunnel_sdk import Tunnel
from flask import Flask

app = Flask(__name__)

@app.route("/hello")
def hello():
    return "Hello from my device!"

if __name__ == "__main__":
    tunnel = Tunnel(
        api_key="", # API KEY
        gateway="ws://127.0.0.1:5000",
        port=5001,
        target_path="/user",
    )

    tunnel.start()
    app.run(port=5001)