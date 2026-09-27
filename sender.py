"""
sender.py -- the covert SENDER (a web client).

Builds the URL request sequence for a secret message from the shared sample
page, then issues those requests as ordinary HTTP GETs against the running
server. The server logs them; the receiver decodes them.

Usage:
    python sender.py "meet at the library at noon"
    python sender.py --server http://127.0.0.1:8000 "attack at dawn"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request

from covert_channel import CovertChannel, CONTROL

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_site", "index.html")


def main():
    ap = argparse.ArgumentParser(description="Covert channel sender")
    ap.add_argument("message", help="secret message (only page-vocabulary words are sent)")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--delay", type=float, default=0.05,
                    help="seconds between requests (mimic normal browsing)")
    args = ap.parse_args()

    with open(SAMPLE, encoding="utf-8") as fh:
        cc = CovertChannel(fh.read())

    enc = cc.encode(args.message)
    if enc["missing"]:
        print(f"[!] not in page vocabulary, skipped: {', '.join(enc['missing'])}",
              file=sys.stderr)

    print(f"[*] secret        : {args.message!r}")
    print(f"[*] URL-number seq : {enc['sequence']}")
    print(f"[*] transmitting {len(enc['urls'])} requests to {args.server} ...\n")

    for num, path in zip(enc["sequence"], enc["urls"]):
        role = CONTROL.get(num, "word/shift")
        url = args.server.rstrip("/") + path
        try:
            urllib.request.urlopen(url, timeout=5).read()
            print(f"    GET {path:<26} #{num:<2} ({role})")
        except Exception as exc:  # noqa: BLE001
            print(f"    GET {path:<26} FAILED: {exc}")
        time.sleep(args.delay)

    print("\n[+] done. The message now lives in the server's request log.")


if __name__ == "__main__":
    main()
