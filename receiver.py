"""
receiver.py -- the covert RECEIVER.

Reads the server's request log (requests.log), rebuilds the dictionaries from
the SAME sample page, isolates the covert segment (between the START and END
control URLs), and decodes it back to plaintext.

This mirrors the paper's receiver, which reconstructs the message from an
Apache access.log or a pcap capture.

Usage:
    python receiver.py                       # decode everything in the log
    python receiver.py --ip 127.0.0.1        # only requests from this client
"""

from __future__ import annotations

import argparse
import json
import os

from covert_channel import CovertChannel, CONTROL

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_site", "index.html")
LOG_PATH = os.path.join(HERE, "requests.log")


def read_log(path, ip=None):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if ip and e.get("ip") != ip:
                continue
            entries.append(e)
    return entries


def main():
    ap = argparse.ArgumentParser(description="Covert channel receiver")
    ap.add_argument("--log", default=LOG_PATH)
    ap.add_argument("--ip", default=None, help="only decode requests from this source IP")
    args = ap.parse_args()

    with open(SAMPLE, encoding="utf-8") as fh:
        cc = CovertChannel(fh.read())

    entries = read_log(args.log, args.ip)
    paths = [e["path"] for e in entries]

    print(f"[*] log entries    : {len(entries)}"
          + (f"  (filtered to IP {args.ip})" if args.ip else ""))
    print("[*] captured request sequence:")
    for e in entries:
        role = CONTROL.get(e["num"], "word/shift")
        print(f"      #{e['num']:<2} {e['path']:<26} ({role})  from {e.get('ip')}")

    message = cc.decode_from_urls(paths)
    print("\n[+] RECOVERED MESSAGE:")
    print(f"    {message!r}")


if __name__ == "__main__":
    main()
