---
name: CSRF middleware body consumption bug
description: BaseHTTPMiddleware calling await request.form() consumed the ASGI receive stream, causing Form() params to be null in downstream route handlers. Fixed with pure ASGI + body replay.
---

# CSRF Middleware Body Consumption

## The rule
Never call `await request.form()` or `await request.body()` inside a `BaseHTTPMiddleware.dispatch()`. The downstream route handler receives a **different** Request object (created from a wrapped receive channel), so even though Starlette caches `request._form` on the middleware's Request object, the route handler's Request sees an empty body and raises 422.

**Why:** `BaseHTTPMiddleware` wraps the ASGI `receive` callable for each middleware layer. Consuming the stream in one layer's Request object does not populate the next layer's Request object — they are independent wrappers over the same underlying stream.

**How to apply:** Any middleware that needs to read a request body must be converted to a **pure ASGI class** (not `BaseHTTPMiddleware`). Buffer the body bytes, then create a `replay_receive` closure that returns the buffered bytes once before falling back to the original `receive`.

## Pattern (pure ASGI body replay)

```python
class MyMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Buffer the full request body
        chunks = []
        more = True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)

        # ... inspect body ...

        # Replay for downstream
        replayed = False
        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
```

## Symptom that triggered this
`POST /security/mfa/confirm` returned FastAPI 422 with `"input":null` for both `totp_secret` and `code` Form() fields. CSRF middleware was consuming the body to read `_csrf` field; route handler saw empty body.

## Fix applied
Converted `CsrfMiddleware` in `app/main.py` from `BaseHTTPMiddleware` to pure ASGI. Header path (`X-CSRF-Token`) skips body reading entirely. Form-body path buffers + replays.
