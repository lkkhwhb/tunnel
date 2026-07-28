from tunnel_sdk import Tunnel
from flask import Flask

app = Flask(__name__)

@app.route("/hello")
def hello():
    return "Hello from my laptop!"

if __name__ == "__main__":
    tunnel = Tunnel(
        api_key="6ac8a47c-76af-4936-851b-5a54c8972f96",
        gateway="ws://127.0.0.1:5000",
        target_path="/bhargav",
    )

    tunnel.run()
    app.run()