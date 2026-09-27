"""
demo.py -- one-shot end-to-end demonstration.

Starts the receiver web server, runs the covert sender for a message, then
runs the receiver to recover it from the server's log -- all automatically.
This is the "just run it and watch the whole pipeline" entry point.

Usage:
    python demo.py
    python demo.py "attack at dawn bring the plans"
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
LOG_PATH = os.path.join(HERE, "requests.log")
SERVER = "http://127.0.0.1:8000"


def wait_for_server(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(SERVER + "/_api/state", timeout=1).read()
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return False


def rule(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "meet at the library at noon"

    # clean slate
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)

    rule("STARTING RECEIVER WEB SERVER")
    server = subprocess.Popen([PY, os.path.join(HERE, "server.py")],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
    try:
        if not wait_for_server():
            print("Server did not start in time.")
            return 1
        print("Server is up at " + SERVER)

        rule("SENDER  (web client leaks the message via URL requests)")
        subprocess.run([PY, os.path.join(HERE, "sender.py"), message], check=True)

        rule("RECEIVER  (recovers the message from the server's request log)")
        subprocess.run([PY, os.path.join(HERE, "receiver.py")], check=True)

        rule("RESULT")
        print(f"Original secret   : {message!r}")
        print("Open the live dashboard while the server runs: " + SERVER)
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
