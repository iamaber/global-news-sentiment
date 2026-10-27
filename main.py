import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
API_PORT = 8000
DASHBOARD_PORT = 8501
SHUTDOWN_TIMEOUT_SECONDS = 5
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _popen_kwargs():
    """Start each child in its own process group so grandchildren can be stopped."""
    if os.name == "posix":
        return {"start_new_session": True}
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}


def _terminate(process):
    """Terminate a child process and everything it spawned."""
    if process.poll() is not None:
        return

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()

    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()


def run_backend(host):
    """Run the FastAPI backend server"""
    backend_dir = Path(__file__).parent / "backend"
    env = os.environ.copy()
    pythonpath = [str(Path(__file__).parent)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api:app",
            "--host",
            host,
            "--port",
            str(API_PORT),
        ],
        cwd=backend_dir,
        env=env,
        **_popen_kwargs(),
    )


def run_frontend(host):
    """Run the single-entry Streamlit dashboard"""
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            str(DASHBOARD_PORT),
            "--server.address",
            host,
        ],
        cwd=Path(__file__).parent,
        **_popen_kwargs(),
    )


def main():
    parser = argparse.ArgumentParser(description="Real-time News Sentiment Analysis")
    parser.add_argument(
        "--mode",
        choices=["all", "backend", "frontend"],
        default="all",
        help="Run mode (default: all)",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=(
            "Interface to bind (default: 127.0.0.1). Use 0.0.0.0 only when you "
            "intend to expose the unauthenticated API and dashboard."
        ),
    )
    args = parser.parse_args()

    if args.host not in LOOPBACK_HOSTS:
        print(
            f"Warning: binding to {args.host} exposes the API and dashboard "
            "beyond this machine. The API has no authentication.",
            file=sys.stderr,
        )

    processes = []

    try:
        if args.mode in ["all", "backend"]:
            backend_process = run_backend(args.host)
            processes.append(backend_process)

            if args.mode == "all":
                time.sleep(3)

        if args.mode in ["all", "frontend"]:
            frontend_process = run_frontend(args.host)
            processes.append(frontend_process)

        for process in processes:
            process.wait()

    except KeyboardInterrupt:
        for process in processes:
            _terminate(process)


if __name__ == "__main__":
    main()
