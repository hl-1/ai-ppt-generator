"""Initialize and manage local development services from any working directory."""

import argparse
import ctypes
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
STATE = LOCAL / "runtime" / "dev-processes.json"
SERVICES = {
    "api": (
        "backend",
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "39800",
        ],
        39800,
    ),
    "worker": ("backend", ["uv", "run", "arq", "app.worker.settings.WorkerSettings"], None),
    "web": (
        "frontend",
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "39173", "--strictPort"],
        39173,
    ),
}


def executable(name):
    result = shutil.which(name + ".cmd" if os.name == "nt" and name in {"npm", "mvn"} else name)
    if not result:
        raise RuntimeError(f"Required command is unavailable: {name}")
    return result


def run(command, directory=ROOT):
    subprocess.run([executable(command[0]), *command[1:]], cwd=directory, check=True)


def compose(*args):
    run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "ops/compose/docker-compose.yml"),
            *args,
        ]
    )


def initialize():
    for name in ("logs", "reports", "screenshots", "scratch", "runtime"):
        (LOCAL / name).mkdir(parents=True, exist_ok=True)
    for directory in (ROOT, ROOT / "backend"):
        if not (directory / ".env").exists():
            shutil.copyfile(directory / ".env.example", directory / ".env")


def install():
    initialize()
    run(["uv", "sync"], ROOT / "backend")
    for directory in ("tools/diagram-engine", "frontend"):
        run(["npm", "ci", "--no-audit", "--no-fund"], ROOT / directory)


def alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def read_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def process_identity(pid):
    """Identify the process creation time so stale PID files can't stop another app."""
    if not alive(pid):
        return None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [
            ctypes.POINTER(ctypes.c_ulonglong)
        ] * 4
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            times = [ctypes.c_ulonglong() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                return None
            return str(times[0].value)
        finally:
            kernel.CloseHandle(handle)
    stat = Path(f"/proc/{pid}/stat")
    try:
        if stat.exists():
            return stat.read_text().rsplit(")", 1)[1].split()[19]
        return subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def owned_process(record):
    return (
        isinstance(record, dict)
        and record.get("identity") is not None
        and process_identity(record["pid"]) == record["identity"]
    )


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.25)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def stop():
    for name, record in read_state().items():
        if not owned_process(record):
            continue
        pid = record["pid"]
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"], check=True, stdout=subprocess.DEVNULL
            )
        else:
            os.killpg(pid, signal.SIGTERM)
            deadline = time.monotonic() + 10
            while owned_process(record) and time.monotonic() < deadline:
                time.sleep(0.1)
            if owned_process(record):
                os.killpg(pid, signal.SIGKILL)
        print(f"Stopped {name} (PID {pid})")
    STATE.unlink(missing_ok=True)


def start():
    initialize()
    state = read_state()
    if any(owned_process(record) for record in state.values()):
        raise RuntimeError("Managed services are already running; use restart or stop first.")
    for _, _, port in SERVICES.values():
        if port and listening(port):
            raise RuntimeError(f"Port {port} is occupied. Stop the existing project service first.")
    compose("up", "-d", "--wait")
    run(["uv", "run", "alembic", "upgrade", "head"], ROOT / "backend")
    state = {}
    try:
        for name, (directory, command, _) in SERVICES.items():
            with (LOCAL / "logs" / f"{name}.log").open("ab") as output:
                options = (
                    {"creationflags": subprocess.CREATE_NO_WINDOW}
                    if os.name == "nt"
                    else {"start_new_session": True}
                )
                process = subprocess.Popen(
                    [executable(command[0]), *command[1:]],
                    cwd=ROOT / directory,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    **options,
                )
            state[name] = {"pid": process.pid, "identity": process_identity(process.pid)}
            STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if any(not owned_process(record) for record in state.values()):
                raise RuntimeError("A service exited. See .local/logs/.")
            if all(listening(port) for _, _, port in SERVICES.values() if port):
                print(
                    "Web: http://127.0.0.1:39173\nAPI: http://127.0.0.1:39800\nLogs: .local/logs/"
                )
                return
            time.sleep(0.5)
        raise RuntimeError("Startup timed out. See .local/logs/.")
    except BaseException:
        stop()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "install", "start", "stop", "restart"))
    args = parser.parse_args()
    if args.action == "init":
        initialize()
    elif args.action == "install":
        install()
    elif args.action == "stop":
        stop()
    else:
        if args.action == "restart":
            stop()
        start()


if __name__ == "__main__":
    main()
