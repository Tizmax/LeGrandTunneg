"""Bounded, non-queuing REST body admission and absolute stream deadlines."""

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import ClientDisconnect, Request

from app.api import rooms
from app.core.limits import TokenBucket
from app.core.settings import settings
from app.main import app


@pytest.fixture(autouse=True)
def limits(monkeypatch):
    monkeypatch.setattr(rooms, "body_readers", 0)
    monkeypatch.setattr(rooms, "rest_bucket", TokenBucket(10000, 10000))
    monkeypatch.setattr(settings, "max_rest_body_readers", 2)
    monkeypatch.setattr(settings, "rest_body_timeout_seconds", .04)


def stream(path="/api/rooms"):
    queue = asyncio.Queue()
    started = asyncio.Event()

    async def receive():
        started.set()
        frame = await queue.get()
        if isinstance(frame, Exception):
            raise frame
        return frame

    return Request({"type": "http", "method": "POST", "path": path,
                    "headers": []}, receive), queue, started


def chunk(queue, data, more=False):
    queue.put_nowait({"type": "http.request", "body": data, "more_body": more})


def rejected(exc, status, code):
    assert exc.value.status_code == status
    assert exc.value.detail["code"] == code
    assert exc.value.headers["Cache-Control"] == "no-store"


async def normal_admission():
    request, queue, _ = stream()
    chunk(queue, b'{"pseudo":"Host"}')
    assert await rooms.body(request) == {"pseudo": "Host"}
    assert rooms.body_readers == 0


@pytest.mark.asyncio
async def test_incomplete_stream_timeout_then_normal_admission():
    request, queue, _ = stream()
    chunk(queue, b'{"pseudo":', more=True)
    with pytest.raises(HTTPException) as exc:
        await asyncio.wait_for(rooms.body(request), .5)
    rejected(exc, 408, "request_timeout")
    await normal_admission()


@pytest.mark.asyncio
async def test_slow_chunks_do_not_renew_absolute_deadline():
    request, queue, started = stream()
    running = asyncio.create_task(rooms.body(request))
    await started.wait()
    # Feed more frequently than the timeout for longer than the total deadline.
    async def feed():
        while True:
            chunk(queue, b" ", more=True)
            await asyncio.sleep(.005)

    feeding = asyncio.create_task(feed())
    try:
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(running, .2)
        rejected(exc, 408, "request_timeout")
        assert not feeding.done()
    finally:
        feeding.cancel()
        await asyncio.gather(feeding, return_exceptions=True)
    await normal_admission()


@pytest.mark.asyncio
async def test_process_capacity_shared_create_join_resume_without_receive_or_queue(monkeypatch):
    monkeypatch.setattr(settings, "rest_body_timeout_seconds", 1)
    active = []
    try:
        for path in ("/api/rooms", "/api/rooms/ABCD/join"):
            request, _, started = stream(path)
            active.append(asyncio.create_task(rooms.body(request)))
            await started.wait()
        assert rooms.body_readers == 2
        for path in ("/api/rooms", "/api/rooms/ABCD/join"):
            request, _, started = stream(path)
            with pytest.raises(HTTPException) as exc:
                await asyncio.wait_for(rooms.body(request), .1)
            rejected(exc, 503, "capacity_exceeded")
            assert not started.is_set()
            assert rooms.body_readers == 2
    finally:
        for task in active:
            task.cancel()
        results = await asyncio.gather(*active, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
    await normal_admission()


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", ["success", "invalid-json", "invalid-shape", "too-large", "disconnect", "error"])
async def test_reader_release_on_every_completion_branch(branch):
    request, queue, _ = stream()
    if branch == "disconnect":
        queue.put_nowait({"type": "http.disconnect"})
        expected = ClientDisconnect
    elif branch == "error":
        queue.put_nowait(OSError("Read failed"))
        expected = OSError
    else:
        raw = {"success": b"{}", "invalid-json": b"{", "invalid-shape": b"[]",
               "too-large": b" " * 8193}[branch]
        chunk(queue, raw)
        expected = HTTPException
    if branch == "success":
        assert await rooms.body(request) == {}
    else:
        with pytest.raises(expected) as exc:
            await rooms.body(request)
        if expected is HTTPException:
            rejected(exc, 413 if branch == "too-large" else 422,
                     "payload_too_large" if branch == "too-large" else "invalid_payload")
    await normal_admission()


@pytest.mark.asyncio
async def test_rate_denied_does_not_acquire_reader():
    rooms.rest_bucket = TokenBucket(.001, 1)
    assert rooms.rest_bucket.consume()
    request, _, started = stream()
    with pytest.raises(HTTPException) as exc:
        await rooms.body(request)
    rejected(exc, 429, "rate_limited")
    assert rooms.body_readers == 0 and not started.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/rooms", "/api/rooms/ABCD/join"])
@pytest.mark.parametrize("saturated", [False, True])
async def test_http_body_admission_errors_are_structured_no_store(path, saturated, monkeypatch):
    receive_started = asyncio.Event()
    if saturated:
        monkeypatch.setattr(rooms, "body_readers", settings.max_rest_body_readers)
    initial_readers = rooms.body_readers
    frames = []

    async def receive():
        receive_started.set()
        await asyncio.Event().wait()

    async def send(frame):
        frames.append(frame)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "headers": [], "server": ("testserver", 80),
             "client": ("127.0.0.1", 1234)}
    await asyncio.wait_for(app(scope, receive, send), .5)
    start = frames[0]
    assert start["status"] == (503 if saturated else 408)
    assert dict(start["headers"])[b"cache-control"] == b"no-store"
    data = json.loads(b"".join(frame.get("body", b"") for frame in frames[1:]))
    assert data == {"detail": {
        "code": "capacity_exceeded" if saturated else "request_timeout",
        "message": "Body reader capacity exceeded." if saturated else "Request body timed out.",
    }}
    assert receive_started.is_set() is not saturated
    assert rooms.body_readers == initial_readers
