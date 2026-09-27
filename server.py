"""
server.py -- the RECEIVER-side web server for the covert channel demo.

Roles it plays:
  * Serves the (unmodified) sample web page and its assets.
  * Logs every request to a page URL into requests.log  (this is the
    "access log / pcap" the receiver later reads to recover the message).
  * Hosts a projector-friendly teaching DASHBOARD at "/" that shows the
    dictionaries, lets you type a secret, transmit it straight from the
    browser, and watch the server decode it live from its own log.

Run:
    python server.py            # http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
import time
from flask import Flask, request, jsonify, Response

from covert_channel import CovertChannel, CONTROL

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_site", "index.html")
# Log location is configurable so the same app runs on a read-only serverless
# host (e.g. Vercel) by pointing COVERT_LOG at /tmp.
LOG_PATH = os.environ.get("COVERT_LOG", os.path.join(HERE, "requests.log"))

with open(SAMPLE, encoding="utf-8") as fh:
    PAGE_HTML = fh.read()

cc = CovertChannel(PAGE_HTML)
DICT_PATHS = set(cc.num_by_url)  # the set of "real" page URLs

app = Flask(__name__)


# --------------------------------------------------------------------------
# Request capture: log every hit to a real page URL (this is the covert
# receiver's raw material). Dashboard/API traffic is ignored.
# --------------------------------------------------------------------------
@app.before_request
def _capture():
    if request.path in DICT_PATHS:
        line = json.dumps({
            "ts": round(time.time(), 3),
            "ip": request.remote_addr,
            "path": request.path,
            "num": cc.num_by_url[request.path],
        })
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _read_log():
    if not os.path.exists(LOG_PATH):
        return []
    out = []
    with open(LOG_PATH, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    return out


# --------------------------------------------------------------------------
# Serve the sample page + stubs for every dictionary URL (so any covert
# request returns 200 and looks like an ordinary page load).
# --------------------------------------------------------------------------
@app.route("/index.html")
def index_html():
    return Response(PAGE_HTML, mimetype="text/html")


@app.route("/<path:anypath>")
def any_dict_url(anypath):
    p = "/" + anypath
    if p in DICT_PATHS:
        return Response(f"<!-- {p} -->", mimetype="text/html")
    return Response("not found", status=404)


# --------------------------------------------------------------------------
# JSON API used by the dashboard
# --------------------------------------------------------------------------
@app.get("/_api/state")
def api_state():
    log = _read_log()
    paths = [e["path"] for e in log]
    decoded = cc.decode_from_urls(paths) if paths else ""
    return jsonify({
        "n": cc.n, "base": cc.base, "max_words": cc.max_words,
        "sendable": len(cc.word_to_tokens),
        "url_dictionary": [
            {"num": i, "url": u, "role": CONTROL.get(i, "word/shift")}
            for i, u in cc.url_by_num.items()
        ],
        "log": log,
        "decoded": decoded,
    })


@app.get("/_api/encode")
def api_encode():
    msg = request.args.get("msg", "")
    return jsonify(cc.encode(msg))


@app.get("/_api/reset")
def api_reset():
    open(LOG_PATH, "w").close()
    return jsonify({"ok": True})


@app.get("/_api/vocab")
def api_vocab():
    return jsonify(sorted(cc.word_to_tokens))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.get("/")
def dashboard():
    return Response(DASHBOARD_HTML, mimetype="text/html")


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Webpage-Source Covert Channel - Live Demo</title>
<style>
  :root{--bg:#0f1420;--panel:#1a2130;--ink:#e8edf6;--muted:#8fa0bd;
        --accent:#5db0ff;--start:#37d67a;--wait:#ffb454;--end:#ff6b6b;--word:#5db0ff;}
  *{box-sizing:border-box}
  body{margin:0;font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
       background:var(--bg);color:var(--ink);padding:24px;max-width:1150px;margin:auto}
  h1{font-size:24px;margin:0 0 4px} .sub{color:var(--muted);margin:0 0 20px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:820px){.grid{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid #26304a;border-radius:12px;padding:16px}
  .card h2{font-size:14px;text-transform:uppercase;letter-spacing:.06em;
           color:var(--muted);margin:0 0 12px}
  input[type=text]{width:100%;padding:11px 12px;border-radius:8px;border:1px solid #33405f;
       background:#0c111b;color:var(--ink);font-size:16px}
  button{margin-top:10px;padding:10px 16px;border:0;border-radius:8px;background:var(--accent);
       color:#03121f;font-weight:600;cursor:pointer;font-size:15px}
  button.ghost{background:#2a3550;color:var(--ink)}
  .seq{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
  .tok{padding:4px 9px;border-radius:6px;font:600 13px ui-monospace,monospace;color:#04121f}
  .tok.start{background:var(--start)} .tok.wait{background:var(--wait)}
  .tok.end{background:var(--end)} .tok.word{background:var(--word)}
  .wordgrp{display:inline-flex;gap:3px;padding:3px;border:1px dashed #45557a;border-radius:8px;margin:3px}
  .wordgrp .lbl{align-self:center;color:var(--muted);font-size:12px;padding:0 4px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  td,th{padding:4px 8px;border-bottom:1px solid #26304a;text-align:left}
  th{color:var(--muted);font-weight:600}
  code{background:#0c111b;padding:1px 5px;border-radius:4px;font-size:13px}
  .decoded{font-size:22px;font-weight:700;color:var(--start);min-height:30px;word-break:break-word}
  .miss{color:var(--end);font-size:13px} .log{max-height:230px;overflow:auto}
  .pill{display:inline-block;background:#0c111b;border:1px solid #33405f;border-radius:20px;
        padding:2px 10px;margin:2px;font-size:12px;color:var(--muted)}
  .legend span{margin-right:14px;font-size:12px;color:var(--muted)}
  .dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:middle}
</style></head>
<body>
  <h1>Webpage-Source Based Covert Channel</h1>
  <p class="sub">The page is never modified. The secret rides entirely in the
     <b>order of URL requests</b> the server sees in its log.</p>

  <div class="grid">
    <div class="card">
      <h2>1 &middot; Sender (this browser = web client)</h2>
      <input id="msg" type="text" placeholder="Type a secret, e.g. meet at the library at noon"
             value="meet at the library at noon">
      <div class="legend" style="margin-top:8px">
        <span><i class="dot" style="background:var(--start)"></i>START</span>
        <span><i class="dot" style="background:var(--wait)"></i>WAIT</span>
        <span><i class="dot" style="background:var(--end)"></i>END</span>
        <span><i class="dot" style="background:var(--word)"></i>word / shift</span>
      </div>
      <div id="seq" class="seq"></div>
      <div id="miss" class="miss"></div>
      <button onclick="transmit()">Transmit from browser &rarr;</button>
      <button class="ghost" onclick="resetLog()">Reset log</button>
    </div>

    <div class="card">
      <h2>2 &middot; Receiver (decoded live from the server log)</h2>
      <div id="decoded" class="decoded">&mdash;</div>
      <p class="sub" style="margin:10px 0 0">Recovered by reading requests.log,
         keeping the segment between the START and END control URLs, and
         reversing the dictionaries.</p>
      <h2 style="margin-top:16px">Captured request log</h2>
      <div class="log"><table id="log"><tbody></tbody></table></div>
    </div>
  </div>

  <div class="card" style="margin-top:18px">
    <h2>URL dictionary <span id="stats" class="sub"></span></h2>
    <table id="urls"><thead><tr><th>#</th><th>URL</th><th>role</th></tr></thead><tbody></tbody></table>
  </div>

<script>
const $ = s => document.querySelector(s);
let URLNUM = {}; // path -> num

async function refresh(){
  const s = await (await fetch('/_api/state')).json();
  $('#stats').textContent =
     `n=${s.n} URLs · word URLs=${s.base} · capacity=${s.max_words} · sendable=${s.sendable}`;
  // url table
  const ub = $('#urls tbody'); ub.innerHTML='';
  s.url_dictionary.forEach(r=>{
    URLNUM[r.url]=r.num;
    ub.insertAdjacentHTML('beforeend',
      `<tr><td><code>${r.num}</code></td><td><code>${r.url}</code></td><td>${r.role}</td></tr>`);
  });
  // log table
  const lb = $('#log tbody'); lb.innerHTML='';
  s.log.forEach(e=>{
    const role = ({0:'START',1:'WAIT',2:'END'})[e.num] || 'word/shift';
    lb.insertAdjacentHTML('beforeend',
      `<tr><td><code>${e.num}</code></td><td><code>${e.path}</code></td><td>${role}</td><td>${e.ip}</td></tr>`);
  });
  $('#decoded').textContent = s.decoded || '—';
  preview();
}

async function preview(){
  const msg = $('#msg').value;
  const e = await (await fetch('/_api/encode?msg='+encodeURIComponent(msg))).json();
  const box = $('#seq'); box.innerHTML='';
  const cls = n => n===0?'start':n===1?'wait':n===2?'end':'word';
  box.insertAdjacentHTML('beforeend', tok(0,'start'));
  e.breakdown.forEach(b=>{
    if(!b.sendable) return;
    if(b.tokens.length===1){ box.insertAdjacentHTML('beforeend', tok(b.tokens[0],'word',b.word)); }
    else {
      let g = `<span class="wordgrp"><span class="lbl">${b.word}</span>`;
      b.tokens.forEach(t=> g+=tok(t,cls(t)));
      g+='</span>'; box.insertAdjacentHTML('beforeend', g);
    }
  });
  box.insertAdjacentHTML('beforeend', tok(2,'end'));
  $('#miss').textContent = e.missing.length ?
     ('not in page vocabulary (cannot be sent): '+e.missing.join(', ')) : '';
}
function tok(n,c,title=''){return `<span class="tok ${c}" title="${title}">${n}</span>`}

async function transmit(){
  const msg = $('#msg').value;
  const e = await (await fetch('/_api/encode?msg='+encodeURIComponent(msg))).json();
  await fetch('/_api/reset');
  // fire the covert requests IN ORDER, just like a real client browsing.
  for(const u of e.urls){ await fetch(u, {cache:'no-store'}); }
  await refresh();
}
async function resetLog(){ await fetch('/_api/reset'); await refresh(); }

$('#msg').addEventListener('input', preview);
refresh();
</script>
</body></html>"""


if __name__ == "__main__":
    print(f"Sample page   : {SAMPLE}")
    print(f"URLs (n)      : {cc.n}   word URLs (n-3): {cc.base}   capacity: {cc.max_words}")
    print(f"Request log   : {LOG_PATH}")
    print("Dashboard     : http://127.0.0.1:8000/")
    app.run(host="127.0.0.1", port=8000, debug=False)
