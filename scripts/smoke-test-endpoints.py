#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from urllib import error, parse, request


BASE_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 5


@dataclass
class Check:
    method: str
    path: str
    expected: set[int]
    body: dict | None = None
    headers: dict | None = None


CHECKS = [
    Check("GET", "/api/health", {200}),
    Check(
        "OPTIONS",
        "/api/download-library",
        {200, 204},
        headers={
            "Origin": "moz-extension://local-smoke-test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    ),
    Check("POST", "/api/download-library", {400}, {"url": "not-a-url"}),
    Check("GET", "/api/library/songs", {200}),
    Check("GET", "/api/library/stream?" + parse.urlencode({"path": "../../etc/passwd"}), {400, 403}),
]


def _request(check: Check) -> tuple[int, str]:
    data = None
    headers = dict(check.headers or {})
    if check.body is not None:
        data = json.dumps(check.body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(
        BASE_URL + check.path,
        data=data,
        headers=headers,
        method=check.method,
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            text = resp.read(300).decode("utf-8", "replace")
            return resp.status, text
    except error.HTTPError as exc:
        text = exc.read(300).decode("utf-8", "replace")
        return exc.code, text


def main() -> int:
    try:
        _request(Check("GET", "/api/health", {200}))
    except error.URLError:
        print("Backend offline — start server on localhost:8000")
        return 2

    failed = 0
    for check in CHECKS:
        try:
            status, text = _request(check)
        except error.URLError as exc:
            failed += 1
            print(f"{check.method} {check.path} -> FAIL offline: {exc.reason}")
            continue

        ok = status in check.expected
        if not ok:
            failed += 1
        label = "OK" if ok else "FAIL"
        message = text.replace("\n", " ")[:160]
        print(f"{check.method} {check.path} -> {status} {label} {message}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
