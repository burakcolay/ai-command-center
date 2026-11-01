from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from acc import config
from acc.api import orchestrator, router
from acc.db import init_db
from acc.events import broker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    orchestrator.recover()
    yield


app = FastAPI(title="AI Command Center", lifespan=lifespan)


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    # Blocks DNS-rebinding: a web page can't reach this API through a fake hostname.
    host = request.headers.get("host", "")
    if not host.startswith(("127.0.0.1:", "localhost:")):
        return JSONResponse({"detail": "Yalnızca localhost"}, status_code=403)
    return await call_next(request)


app.include_router(router)


@app.websocket("/ws")
async def ws(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
        await socket.close(code=1008)
        return
    await socket.accept()
    q = broker.subscribe()
    try:
        while True:
            await socket.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(q)


if config.WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=config.WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (config.WEB_DIST / path).resolve()
        if path and f.is_file() and f.is_relative_to(config.WEB_DIST):
            return FileResponse(f)
        return FileResponse(config.WEB_DIST / "index.html")


def run() -> None:
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    run()
