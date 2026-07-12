"""Reference web app for Tier 3 E2E tests.

A simple FastAPI app with intentional quirks for self-healing and failure-analysis tests:
- A login page with accessible selectors (id="username", id="password")
- A page with broken ID for healing tests (id changes every request)
- An endpoint that randomly fails for flake detection
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AQIP Reference App")


class LoginRequest(BaseModel):
    username: str
    password: str


class ItemRequest(BaseModel):
    name: str
    price: float


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> dict[str, Any]:
    return {
        "title": "AQIP Reference",
        "endpoints": [
            "/health",
            "/login",
            "/items",
            "/secret/{id}",
        ],
    }


@app.post("/login")
def login(req: LoginRequest) -> dict[str, Any]:
    if req.username == "admin" and req.password == "secret":
        return {"status": "ok", "token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="invalid credentials")


_items: list[dict[str, Any]] = []


@app.get("/items")
def list_items() -> dict[str, Any]:
    return {"items": _items, "count": len(_items)}


@app.post("/items")
def create_item(req: ItemRequest) -> dict[str, Any]:
    if req.price < 0:
        raise HTTPException(status_code=400, detail="price must be non-negative")
    item = {"id": len(_items) + 1, "name": req.name, "price": req.price}
    _items.append(item)
    return item


@app.get("/secret/{secret_id}")
def get_secret(secret_id: str) -> dict[str, Any]:
    """Endpoint whose response shape changes based on secret_id to test self-healing.

    For odd IDs, the response uses {value: ...}; for even IDs, {data: ...}.
    """
    if secret_id.isdigit() and int(secret_id) % 2 == 0:
        return {"data": f"secret-{secret_id}"}
    return {"value": f"secret-{secret_id}"}


@app.get("/unstable")
def unstable() -> dict[str, Any]:
    """Returns 500 ~50% of the time. Used to test failure classification."""
    import random

    if random.random() < 0.5:
        raise HTTPException(status_code=500, detail="intermittent failure")
    return {"ok": True}


@app.post("/echo")
def echo(payload: dict) -> dict:
    return {"echo": payload}


# Serve a simple HTML for DOM-extraction tests
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>AQIP Reference</title></head>
<body>
  <header>
    <h1 id="title">AQIP Reference App</h1>
    <nav><a href="/login" id="nav-login">Login</a></nav>
  </header>
  <main>
    <section id="items-section">
      <h2>Items</h2>
      <button id="add-item-btn" aria-label="Add item">+</button>
      <ul id="items-list"></ul>
    </section>
    <form id="login-form" action="/login" method="post">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" />
      <label for="password">Password</label>
      <input id="password" name="password" type="password" />
      <button type="submit" id="submit-btn">Sign in</button>
    </form>
  </main>
</body>
</html>
"""


@app.get("/page", response_class=None)
def page():
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=INDEX_HTML)


def reset_state() -> None:
    """Reset in-memory state. For test isolation."""
    _items.clear()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8765")))