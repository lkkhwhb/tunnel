import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from tunnel_sdk import Tunnel

tunnel = Tunnel.from_env()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the tunnel in the background when FastAPI starts
    print("Starting Tunnel SDK...")
    tunnel.start()
    yield
    # Gracefully stop the tunnel when FastAPI shuts down
    print("Shutting down Tunnel SDK...")
    tunnel.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/api/hello")
async def hello():
    return {"message": "Hello from FastAPI through the Tunnel Gateway!"}

if __name__ == "__main__":
    # Ensure TUNNEL_GATEWAY, TUNNEL_API_KEY, TUNNEL_TARGET_PATH, 
    # and TUNNEL_LOCAL_URL (e.g., http://127.0.0.1:8000) are set.
    uvicorn.run("fastapi_app:app", port=8000, reload=False)
