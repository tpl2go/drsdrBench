from __future__ import annotations

import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path("/workspace")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SERVER_STARTUP_TIMEOUT_SECONDS = 60.0


def env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid {name}: {raw_value!r}") from exc


def load_json_response(req: urllib.request.Request) -> Any:
    try:
        with urllib.request.urlopen(req) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenCode request failed: {exc.code} {exc.reason}: {body}"
        ) from exc

    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def make_request(
    method: str,
    host: str,
    port: int,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> urllib.request.Request:
    url = f"http://{host}:{port}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    headers = {"Accept": "application/json"}
    server_password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if server_password:
        username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        token = base64.b64encode(f"{username}:{server_password}".encode("utf-8")).decode(
            "ascii"
        )
        headers["Authorization"] = f"Basic {token}"

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    return urllib.request.Request(url, data=data, headers=headers, method=method)


def request_json(
    method: str,
    host: str,
    port: int,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    return load_json_response(make_request(method, host, port, path, query=query, body=body))


def create_session(host: str, port: int, directory: Path, title: str) -> dict[str, Any]:
    return request_json(
        "POST",
        host,
        port,
        "/session",
        query={"directory": str(directory)},
        body={"title": title},
    )


def send_prompt(
    host: str,
    port: int,
    directory: Path,
    session_id: str,
    prompt_text: str,
) -> Any:
    return request_json(
        "POST",
        host,
        port,
        f"/session/{session_id}/prompt_async",
        query={"directory": str(directory)},
        body={
            "parts": [
                {
                    "type": "text",
                    "text": prompt_text,
                }
            ],
        },
    )


def session_messages_snapshot(
    host: str,
    port: int,
    directory: Path,
    session_id: str,
) -> Any:
    return request_json(
        "GET",
        host,
        port,
        f"/session/{session_id}/message",
        query={"directory": str(directory)},
    )


def message_created_time(message: Any) -> float:
    if not isinstance(message, dict):
        return float("-inf")
    info = message.get("info")
    if not isinstance(info, dict):
        return float("-inf")
    time_value = info.get("time")
    if not isinstance(time_value, dict):
        return float("-inf")
    created = time_value.get("created")
    if isinstance(created, (int, float)):
        return float(created)
    return float("-inf")


def latest_session_message(messages_payload: Any) -> Any:
    if not isinstance(messages_payload, list) or not messages_payload:
        return None
    return max(messages_payload, key=message_created_time)


def wait_for_completion(
    host: str,
    port: int,
    directory: Path,
    session_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> None:
    timeout_deadline = time.time() + timeout_seconds
    seen_message_created_times: set[float] = set()

    seen_busy = False

    while time.time() < timeout_deadline:
        status_map = request_json(
            "GET",
            host,
            port,
            "/session/status",
            query={"directory": str(directory)},
        )
        if isinstance(status_map, dict):
            status_payload = status_map.get(session_id)

            if status_payload is not None and status_payload.get("type") == "busy":
                seen_busy = True


        if seen_busy:
            messages_payload = session_messages_snapshot(host, port, directory, session_id)
            latest_message = latest_session_message(messages_payload)
            latest_message_created_time = message_created_time(latest_message)
            if (
                latest_message is not None
                and latest_message_created_time != float("-inf")
                and latest_message_created_time not in seen_message_created_times
            ):
                print("", flush=True)
                print(json.dumps(latest_message, indent=2))
                seen_message_created_times.add(latest_message_created_time)
            if status_payload is None or (status_payload.get("type") not in ("busy", "retry")):
                print()
                return 
            else:
                time.sleep(poll_interval_seconds)
                print(".", end="", flush=True)
        else:
            print("x", end="", flush=True)
        

    raise RuntimeError(
        f"OpenCode session {session_id} did not complete within {timeout_seconds} seconds"
    )


def run_export(cmd: list[str], output_path: Path, cwd: Path | None = None) -> None:
    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            subprocess.run(
                cmd,
                cwd=cwd,
                check=True,
                stdout=output_file,
                stderr=subprocess.PIPE,
                text=True,
            )
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
        raise


def choose_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def start_opencode_server(host: str, port: int, cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["opencode", "serve", "--hostname", host, "--port", str(port)],
        cwd=cwd,
        text=True,
        start_new_session=True,
    )


def stop_opencode_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except PermissionError:
            process.kill()
        process.wait(timeout=10)


def main() -> None:
    config_path = WORKSPACE / "opencode.json"
    prompt_path = WORKSPACE / "prompt.txt"
    if not config_path.exists():
        raise RuntimeError(f"Missing config: {config_path}")
    if not prompt_path.exists():
        raise RuntimeError(f"Missing prompt: {prompt_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = config.get("model")
    if not isinstance(model, str) or not model:
        raise RuntimeError("opencode.json does not define a valid model")

    opencode_host = os.environ.get("OPENCODE_HOST", DEFAULT_HOST)
    poll_interval_seconds = env_float("OPENCODE_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)
    server_startup_timeout_seconds = env_float(
        "OPENCODE_SERVER_STARTUP_TIMEOUT_SECONDS",
        DEFAULT_SERVER_STARTUP_TIMEOUT_SECONDS,
    )

    opencode_port = choose_free_port(opencode_host)
    server_process = start_opencode_server(opencode_host, opencode_port, WORKSPACE)
    print(f"{WORKSPACE.name}: opencode server started at {opencode_host}:{opencode_port}")
    try:
        deadline = time.time() + server_startup_timeout_seconds
        last_error: Exception | None = None
        while time.time() < deadline:
            if server_process.poll() is not None:
                raise RuntimeError(
                    "OpenCode server process exited before becoming healthy"
                ) from last_error
            try:
                health = request_json("GET", opencode_host, opencode_port, "/global/health")
                if isinstance(health, dict) and health.get("healthy") is True:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(0.5)
        else:
            raise RuntimeError(
                f"OpenCode server at http://{opencode_host}:{opencode_port} did not become healthy"
            ) from last_error

        session = create_session(opencode_host, opencode_port, WORKSPACE, WORKSPACE.name)
        session_id = session.get("id") or session.get("sessionID")
        if not isinstance(session_id, str) or not session_id:
            raise RuntimeError(f"OpenCode did not return a session id: {session}")

        print(f"{WORKSPACE.name}: created session {session_id} using {model}")

        prompt_text = prompt_path.read_text(encoding="utf-8")
        send_prompt(
            opencode_host,
            opencode_port,
            WORKSPACE,
            session_id,
            prompt_text,
        )

        wait_for_completion(
            opencode_host,
            opencode_port,
            WORKSPACE,
            session_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=60 * 60,
        )

        messages = session_messages_snapshot(opencode_host, opencode_port, WORKSPACE, session_id)
        run_export(
            ["opencode", "export", session_id],
            Path("opencode_session.json"),
            cwd=WORKSPACE,
        )
        print(f"{WORKSPACE.name}: exported")
    finally:
        stop_opencode_server(server_process)


if __name__ == "__main__":
    main()
