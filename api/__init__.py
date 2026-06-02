from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from api.routes import router as _http_router
from api.websocket import router as _ws_router, start_run
import api.routes as _routes_mod

# Wire start_run into the routes module (avoids a circular import).
_routes_mod._start_run = start_run

_DASHBOARD = Path(__file__).parent.parent / "dashboard" / "index.html"

app = FastAPI(title="AeroSense ATC", version="0.1.0")
app.include_router(_http_router)
app.include_router(_ws_router)


@app.get("/")
async def dashboard():
    return FileResponse(_DASHBOARD)
