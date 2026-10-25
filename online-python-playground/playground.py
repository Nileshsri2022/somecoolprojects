#!/usr/bin/env python3
"""Online Python Playground — local demo server (stdlib only).

Serves a single editor page on GET / and executes submitted code via
POST /run in a restricted child process (see docs/SPEC.md).

    python3 playground.py [--host 127.0.0.1] [--port 8000]
    PLAYGROUND_TIMEOUT=5 python3 playground.py   # seconds, default 5

Child mode (internal, used by the server to run user code):

    python3 playground.py --child <codefile>

    The code file must live inside the run's temp directory; the child
    chdirs there, installs an audit hook, and prints one JSON envelope
    (the run result) to its real stdout.

SECURITY: this is a LOCAL DEMO sandbox only, not production-grade
sandboxing and not safe for untrusted users. Do not bind it to a
public interface. See docs/SPEC.md for the enforced limits and the
known holes.
"""

import argparse
import io
import json
import os
import re
import resource
import runpy
import subprocess
import sys
import sysconfig
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 5.0
MAX_OUTPUT = 10000

BLOCKED_MODULES = {
    "socket", "subprocess", "multiprocessing", "ctypes", "urllib",
    "http", "ftplib", "smtplib", "requests", "pty", "socketserver",
    "telnetlib", "poplib", "imaplib", "xmlrpc",
    "_socket", "_ssl",
}

BLOCKED_EVENTS = {
    "socket.connect", "socket.connect_ex", "socket.bind", "socket.listen",
    "socket.getaddrinfo", "socket.gethostbyname",
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
    "os.spawnl", "os.spawnle", "os.spawnlp", "os.spawnv", "os.spawnve",
    "os.spawnvp", "os.fork", "os.forkpty", "pty.spawn",
    "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function",
}

PATH_EVENTS = {
    "os.remove", "os.unlink", "os.rename", "os.rmdir", "os.mkdir",
    "os.makedirs", "os.link", "os.symlink", "os.chmod", "os.chown",
    "os.truncate", "os.chdir",
}


def _timeout_seconds():
    try:
        return float(os.environ.get("PLAYGROUND_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


# ---------------------------------------------------------------- child

def _stdlib_dirs():
    dirs = set()
    try:
        paths = sysconfig.get_paths()
        for key in ("stdlib", "platstdlib", "purelib", "platlib"):
            if paths.get(key):
                dirs.add(os.path.realpath(paths[key]))
    except Exception:
        pass
    for prefix in {sys.prefix, sys.base_prefix, sys.exec_prefix}:
        for sub in ("lib", "lib64"):
            candidate = os.path.join(prefix, sub)
            if os.path.isdir(candidate):
                dirs.add(os.path.realpath(candidate))
    return dirs


def _child_audit_hook(workdir, stdlib_dirs):
    def _inside(path, roots):
        real = os.path.realpath(path)
        return any(real == r or real.startswith(r + os.sep) for r in roots)

    def hook(event, args):
        if event in BLOCKED_EVENTS:
            raise PermissionError(
                "blocked by playground sandbox: %s is not allowed" % event)
        if event == "import":
            name = args[0] if args else ""
            top = name.split(".")[0] if isinstance(name, str) else ""
            if top in BLOCKED_MODULES:
                raise PermissionError(
                    "blocked by playground sandbox: import of %r "
                    "is not allowed" % top)
        elif event == "open":
            path = args[0] if args else ""
            if not isinstance(path, str) or path.startswith("<"):
                return
            mode = args[1] if len(args) > 1 else "r"
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            if path == "/dev/null":
                return
            if _inside(path, [workdir]):
                return
            write_mode = any(c in mode for c in "wax+")
            if not write_mode and _inside(path, stdlib_dirs):
                return
            raise PermissionError(
                "blocked by playground sandbox: file access outside "
                "the run directory is not allowed: %s" % path)
        elif event in PATH_EVENTS:
            for arg in args:
                if not isinstance(arg, str) or arg.startswith("<"):
                    continue
                path = arg if os.path.isabs(arg) else os.path.join(
                    os.getcwd(), arg)
                if path == "/dev/null":
                    continue
                if not _inside(path, [workdir]):
                    raise PermissionError(
                        "blocked by playground sandbox: filesystem "
                        "operation outside the run directory is not "
                        "allowed: %s" % path)
    return hook


def _run_child(code_path):
    """Run user code under restrictions; print a JSON envelope."""
    workdir = os.path.dirname(os.path.abspath(code_path))
    os.chdir(workdir)
    sys.addaudithook(_child_audit_hook(workdir, _stdlib_dirs()))
    # The server half of this file imports socket/subprocess/http, so
    # they are already in sys.modules in the child. A cached import
    # would otherwise bypass the audit hook, so purge blocked modules
    # (the child never serves HTTP, so it does not need them).
    for _name in list(sys.modules):
        if _name.split(".")[0] in BLOCKED_MODULES:
            del sys.modules[_name]
    with open(code_path, "r", encoding="utf-8") as fh:
        source = fh.read()
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    result = {"ok": True, "stdout": "", "stderr": "",
              "error": None, "timed_out": False, "truncated": False}
    # Redirect user output away from our envelope channel.
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        try:
            code_obj = compile(source, "<snippet>", "exec")
        except SyntaxError:
            formatted = traceback.format_exc()
            result.update(ok=False, error={
                "type": "SyntaxError",
                "message": str(sys.exc_info()[1]),
                "lineno": sys.exc_info()[1].lineno,
                "traceback": formatted})
        else:
            try:
                runpy.run_path(code_path, run_name="__main__")
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    result.update(ok=False, error={
                        "type": "SystemExit",
                        "message": "exit code %r" % (exc.code,),
                        "lineno": None,
                        "traceback": traceback.format_exc()})
            except BaseException:
                tb = traceback.format_exc()
                exc_type, exc_value, exc_tb = sys.exc_info()
                lineno = None
                for frame in traceback.extract_tb(exc_tb):
                    if frame.filename in (code_path, "<snippet>"):
                        lineno = frame.lineno
                result.update(ok=False, error={
                    "type": exc_type.__name__,
                    "message": str(exc_value),
                    "lineno": lineno,
                    "traceback": tb})
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    result["stdout"] = out_buf.getvalue()
    result["stderr"] = err_buf.getvalue()
    # Envelope goes to the REAL stdout, never the captured buffer.
    print(json.dumps(result), file=sys.__stdout__)
    sys.__stdout__.flush()


def _preexec_limits():
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError):
        pass


def _truncate(text):
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT], True
    return text, False


def run_code(code, timeout=None):
    """Execute `code` in a restricted child; return the result dict."""
    if timeout is None:
        timeout = _timeout_seconds()
    result = {"ok": False, "stdout": "", "stderr": "", "error": None,
              "timed_out": False, "truncated": False}
    with tempfile.TemporaryDirectory(prefix="pyplay-") as tmpdir:
        code_path = os.path.join(tmpdir, "snippet.py")
        with open(code_path, "w", encoding="utf-8") as fh:
            fh.write(code)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmpdir,
            "TMPDIR": tmpdir,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--child", code_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, env=env, cwd=tmpdir,
            preexec_fn=_preexec_limits)
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raw_out, raw_err = proc.communicate()
            result.update(timed_out=True, error={
                "type": "TimeoutError",
                "message": "execution timed out after %g seconds" % timeout,
                "lineno": None, "traceback": ""})
            result["stdout"], trunc = _truncate(
                raw_out.decode("utf-8", "replace"))
            result["truncated"] = trunc
            return result
        text = raw_out.decode("utf-8", "replace")
        try:
            result = json.loads(text.strip().splitlines()[-1]) \
                if text.strip() else result
        except (ValueError, IndexError):
            result.update(error={
                "type": "RuntimeError",
                "message": "execution failed (no result from runner)",
                "lineno": None,
                "traceback": raw_err.decode("utf-8", "replace")})
        if not result.get("ok") and result.get("error") is None:
            result["error"] = {"type": "RuntimeError",
                               "message": "execution failed",
                               "lineno": None, "traceback": ""}
        result["stdout"], t1 = _truncate(result.get("stdout", ""))
        result["stderr"], t2 = _truncate(result.get("stderr", ""))
        result["truncated"] = bool(t1 or t2)
    return result


# ---------------------------------------------------------------- server

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Online Python Playground (local)</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}
body.dark{background:#1e1e1e;color:#ddd}
body.dark textarea,body.dark pre{background:#111;color:#ddd}
textarea{width:100%;height:220px;font-family:monospace;font-size:14px}
pre{white-space:pre-wrap;background:#f4f4f4;padding:1em;overflow:auto}
#error{color:#a00;font-weight:bold}
.kw{color:#0070c0;font-weight:bold}.str{color:#a31515}.num{color:#098658}
.com{color:#008000;font-style:italic}.bi{color:#795e26}
button{margin:0.3em 0.3em 0.3em 0}
</style>
</head>
<body>
<h1>Online Python Playground (local demo)</h1>
<p><strong>Local demo sandbox only</strong> — runs your own code on this
machine with a timeout and restricted file/network access. Not safe for
untrusted users; do not expose it publicly. See README for limits.</p>
<textarea id="editor" placeholder="Write Python here...">print("Hello, World!")</textarea>
<div>
<button id="run-btn">Run (Ctrl+Enter)</button>
<button id="save-btn">Save snippet (Ctrl+S)</button>
<button id="share-btn">Copy share link</button>
<button id="theme-toggle">Toggle dark mode</button>
<button id="clear-btn">Clear output</button>
<input id="snippet-name" placeholder="Snippet name">
</div>
<p id="loading" hidden>Running&hellip;</p>
<h2>Syntax highlight preview</h2>
<pre id="highlight"></pre>
<h2>Output</h2>
<pre id="output"></pre>
<div id="error"></div>
<details><summary>Traceback</summary><pre id="traceback"></pre></details>
<h2>Saved snippets (localStorage)</h2>
<div id="snippet-list"></div>
<h2>Keyboard shortcuts</h2>
<ul>
<li>Ctrl+Enter (Cmd+Enter): Run</li>
<li>Ctrl+S (Cmd+S): Save snippet</li>
<li>Ctrl+Z / Ctrl+Y: Undo / Redo (native editor)</li>
<li>Ctrl+C / Ctrl+V: Copy / Paste</li>
</ul>
<p>Share links use a <code>#code=</code> URL fragment: opening such a link
loads the code into the editor. Snippets are stored only in this browser.</p>
<script>
var editor = document.getElementById('editor');
var highlight = document.getElementById('highlight');
var output = document.getElementById('output');
var errorBox = document.getElementById('error');
var tbBox = document.getElementById('traceback');
var loading = document.getElementById('loading');
var runBtn = document.getElementById('run-btn');
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function highlightCode(code){
  var e = esc(code);
  var re = /(#[^\\n]*)|(&quot;.*?&quot;|'[^'\\n]*')|\\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|with|lambda|pass|break|continue|and|or|not|in|is|None|True|False|raise|yield|global|assert|del)\\b|\\b(print|len|range|str|int|float|list|dict|set|tuple|open|input|type|sum|min|max|abs|sorted|enumerate|zip)\\b|\\b(\\d+(?:\\.\\d+)?)\\b/g;
  return e.replace(re, function(m, com, str, kw, bi, num){
    if(com) return '<span class="com">'+m+'</span>';
    if(str) return '<span class="str">'+m+'</span>';
    if(kw) return '<span class="kw">'+m+'</span>';
    if(bi) return '<span class="bi">'+m+'</span>';
    if(num) return '<span class="num">'+m+'</span>';
    return m;
  });
}
function refreshHighlight(){ highlight.innerHTML = highlightCode(editor.value); }
editor.addEventListener('input', refreshHighlight);
function loadSnippets(){
  try { return JSON.parse(localStorage.getItem('pyplay.snippets') || '{}'); }
  catch(e){ return {}; }
}
function storeSnippets(s){
  try { localStorage.setItem('pyplay.snippets', JSON.stringify(s)); return true; }
  catch(e){ errorBox.textContent = 'Could not save: localStorage is full or unavailable (' + e.message + ')'; return false; }
}
function renderList(){
  var s = loadSnippets();
  var list = document.getElementById('snippet-list');
  list.innerHTML = '';
  Object.keys(s).forEach(function(name){
    var load = document.createElement('button');
    load.textContent = 'Load: ' + name;
    load.onclick = function(){ editor.value = s[name]; refreshHighlight(); };
    var del = document.createElement('button');
    del.textContent = 'Delete: ' + name;
    del.onclick = function(){ var cur = loadSnippets(); delete cur[name]; storeSnippets(cur); renderList(); };
    list.appendChild(load); list.appendChild(del); list.appendChild(document.createElement('br'));
  });
}
async function runCode(){
  loading.hidden = false; runBtn.disabled = true;
  errorBox.textContent = ''; tbBox.textContent = ''; output.textContent = '';
  try {
    var resp = await fetch('/run', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({code: editor.value})});
    var data = await resp.json();
    output.textContent = data.stdout || '';
    if(data.stderr) output.textContent += '\\n[stderr]\\n' + data.stderr;
    if(data.truncated) output.textContent += '\\n[output truncated]';
    if(data.error){
      var msg = data.error.type + ': ' + data.error.message;
      if(data.error.lineno) msg = 'Line ' + data.error.lineno + ': ' + msg;
      if(data.timed_out) msg = 'Timed out: ' + data.error.message;
      errorBox.textContent = msg;
      tbBox.textContent = data.error.traceback || '';
    }
  } catch(e){
    errorBox.textContent = 'Could not reach the playground server \\u2014 is `python3 playground.py` running? (' + e.message + ')';
  }
  loading.hidden = true; runBtn.disabled = false;
}
runBtn.onclick = runCode;
document.getElementById('clear-btn').onclick = function(){ output.textContent=''; errorBox.textContent=''; tbBox.textContent=''; };
document.getElementById('save-btn').onclick = function(){
  var name = document.getElementById('snippet-name').value.trim();
  if(!name){ errorBox.textContent = 'Enter a snippet name first.'; return; }
  var s = loadSnippets(); s[name] = editor.value;
  if(storeSnippets(s)) renderList();
};
document.getElementById('share-btn').onclick = function(){
  var frag = '#code=' + btoa(unescape(encodeURIComponent(editor.value))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
  var url = location.origin + location.pathname + frag;
  navigator.clipboard.writeText(url).then(function(){ errorBox.textContent = 'Share link copied.'; },
    function(){ errorBox.textContent = 'Share link: ' + url; });
};
document.getElementById('theme-toggle').onclick = function(){
  document.body.classList.toggle('dark');
  try { localStorage.setItem('pyplay.dark', document.body.classList.contains('dark') ? '1' : '0'); } catch(e){}
};
try { if(localStorage.getItem('pyplay.dark') === '1') document.body.classList.add('dark'); } catch(e){}
if(location.hash.indexOf('#code=') === 0){
  try {
    var b64 = location.hash.slice(6).replace(/-/g,'+').replace(/_/g,'/');
    editor.value = decodeURIComponent(escape(atob(b64)));
  } catch(e){ errorBox.textContent = 'Could not decode the shared code link.'; }
}
document.addEventListener('keydown', function(e){
  if((e.ctrlKey || e.metaKey) && e.key === 'Enter'){ e.preventDefault(); runCode(); }
  if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's'){ e.preventDefault(); document.getElementById('save-btn').click(); }
});
refreshHighlight();
renderList();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/run":
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/run":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON"})
            return
        code = payload.get("code") if isinstance(payload, dict) else None
        if not isinstance(code, str):
            self._send_json(400, {"error": "code must be a string"})
            return
        self._send_json(200, run_code(code))

    do_PUT = do_DELETE = do_PATCH = lambda self: (
        self.send_response(405), self.send_header("Content-Length", "0"),
        self.end_headers())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--child", metavar="CODEFILE")
    args = parser.parse_args()
    if args.child:
        _run_child(args.child)
        return
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Online Python Playground at http://%s:%d/ "
          "(local demo sandbox only)" % (args.host, server.server_port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
