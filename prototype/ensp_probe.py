"""eNSP Pro API probe - validates reverse-engineered REST + STOMP console protocol.

Usage: python ensp_probe.py <cmd> [args...]
Commands:
  login                      test /api/login
  whoami                     /api/getUserInfo after login
  sandboxes                  POST /service/ensp/sandbox/getByPage
  sandbox <id>               GET /service/ensp/sandbox/getOneSandbox
  avail                      GET /service/ensp/sandbox/getAvailableDevices
  avail-sb <id>              GET /service/ensp/sandbox/getAvailableDevice
  create-sb <name>           POST /service/ensp/sandbox/create
  adddev <sb> <json-file>    POST /service/ensp/device/batchCreate, file = full device object
  link <sb> <json-file>      POST /service/ensp/link/create
  start <sb> <id...>         POST /service/ensp/device/batchStart
  stop <sb> <id...>          POST /service/ensp/device/batchStop
  cli <sb> <node> <cmd...>   STOMP console session
"""
import json
import ssl
import sys
import time
import urllib3

import requests
import websocket

urllib3.disable_warnings()

BASE = "https://192.168.1.20:28443"
USER = "admin"
PW = "Demo@123"

S = requests.Session()
S.verify = False


def show(tag, r):
    print(f"=== {tag} -> HTTP {r.status_code}")
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        try:
            print(json.dumps(r.json(), ensure_ascii=False, indent=1)[:4000])
            return
        except Exception:
            pass
    print(r.text[:800])


def api(method, path, body=None, **kw):
    return S.request(method, BASE + path, json=body if body is not None else None,
                     headers={"Accept-Language": "zh"}, timeout=30, **kw)


def ensure_login():
    if not S.cookies:
        r = S.get(BASE + "/api/login?service=" + BASE + "/home",
                  allow_redirects=True, timeout=30)
        print("session:", r.status_code, dict(S.cookies))


def do_login():
    r = api("GET", "/service/attack/key")
    print("attack/key:", r.status_code, r.text[:200])
    try:
        token = r.json().get("data")
    except Exception:
        token = None
    payload = {"username": USER, "password": PW}
    r = S.post(BASE + "/api/login", json=payload, timeout=30,
               headers={"Accept-Language": "zh", **({"token": token} if token else {})})
    show("LOGIN", r)


def cmd_sandbox(sid):
    r = api("GET", f"/service/ensp/sandbox/getOneSandbox?sandboxId={sid}")
    show("SANDBOX", r)
    d = r.json().get("data") or {}
    for dev in d.get("devices", []):
        ifs = [(i.get("id"), i.get("name")) for i in dev.get("deviceIfs", [])][:6]
        print(f"  node {dev.get('id')} name={dev.get('name')} type={dev.get('deviceTypeId')} "
              f"status={dev.get('status')} ifs={ifs}")


def stomp_cli(sb, node, commands):
    cookie = "; ".join(f"{c.name}={c.value}" for c in S.cookies)
    ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
    ws.connect(f"wss://192.168.1.20:28443/web.socket/000/probe{int(time.time())}/websocket",
               header=[f"Cookie: {cookie}"], origin=BASE, timeout=10)
    cid = f"{sb}/{node}"
    sub_out, sub_hb = f"/user/topic/console/message/{cid}", f"/user/topic/console/heartbeat/{cid}"
    d_connect = f"/app/console/connect/{cid}"
    d_msg, d_hb, d_close = (f"/app/console/message/{cid}",
                            f"/app/console/heartbeat/{cid}", f"/app/console/close/{cid}")

    def frame(cmd, headers, body=""):
        lines = [cmd] + [f"{k}:{v}" for k, v in headers.items()]
        if body:
            lines.append(f"content-length:{len(body.encode())}")
        stomp_text = "\n".join(lines) + "\n\n" + body + "\x00"
        ws.send(json.dumps([stomp_text]))

    def recv_frames(seconds):
        out = []
        end = time.time() + seconds
        while time.time() < end:
            ws.settimeout(max(0.1, end - time.time()))
            try:
                data = ws.recv()
            except Exception:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8", "replace")
            if data == "h":  # sockjs heartbeat
                continue
            if data == "o":
                print("[sockjs open]")
                continue
            if data.startswith("c"):
                print("[sockjs close]", data[:120])
                break
            if data.startswith("a"):
                for item in json.loads(data[1:]):
                    raw = item.strip("\r\n")
                    if not raw:
                        continue
                    head, _, body2 = raw.partition("\n\n")
                    lines = head.split("\n")
                    cmdname = lines[0].strip()
                    headers = dict(l.split(":", 1) for l in lines[1:] if ":" in l)
                    if cmdname == "MESSAGE" and headers.get("destination") == sub_out:
                        out.append(body2)
                    elif cmdname in ("CONNECTED", "ERROR", "RECEIPT"):
                        print(f"[stomp {cmdname}] {head[:160]}")
        return out

    frame("CONNECT", {"accept-version": "1.2", "heart-beat": "30000,30000", "host": "192.168.1.20"})
    recv_frames(4)
    frame("SUBSCRIBE", {"destination": sub_out, "id": "sub-out"})
    frame("SUBSCRIBE", {"destination": sub_hb, "id": "sub-hb"})
    time.sleep(0.3)
    frame("SEND", {"destination": d_connect})
    banner = recv_frames(6)
    print("[banner]", repr("".join(banner))[:600])
    for cmd in commands:
        frame("SEND", {"destination": d_msg}, cmd + "\r")
        out = recv_frames(3.5)
        text = "".join(out)
        print(f"[cmd {cmd!r}]")
        print(text[:3000])
        frame("SEND", {"destination": d_hb})
    frame("SEND", {"destination": d_close})
    ws.close()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    if cmd == "login":
        do_login()
    elif cmd == "whoami":
        ensure_login(); show("WHOAMI", api("GET", "/api/getUserInfo"))
    elif cmd == "sandboxes":
        ensure_login(); show("BY_PAGE", api("POST", "/service/ensp/sandbox/getByPage",
                                            {"pageNum": 1, "pageSize": 20}))
    elif cmd == "sandbox":
        ensure_login(); cmd_sandbox(sys.argv[2])
    elif cmd == "avail":
        ensure_login(); show("AVAIL", api("GET", "/service/ensp/sandbox/getAvailableDevices"))
    elif cmd == "avail-sb":
        ensure_login(); show("AVAIL_SB", api("GET", f"/service/ensp/sandbox/getAvailableDevice?sandboxId={sys.argv[2]}"))
    elif cmd == "create-sb":
        ensure_login(); show("CREATE_SB", api("POST", "/service/ensp/sandbox/create",
                                              {"name": sys.argv[2], "isPublic": 0, "maxVms": 20}))
    elif cmd == "adddev":
        ensure_login()
        dev = json.load(open(sys.argv[3], encoding="utf-8"))
        show("ADDDEV", api("POST", "/service/ensp/device/batchCreate",
                           {"devices": [dev], "sandboxId": int(sys.argv[2])}))
    elif cmd == "link":
        ensure_login()
        obj = json.load(open(sys.argv[3], encoding="utf-8"))
        obj["sandboxId"] = int(sys.argv[2])
        show("LINK", api("POST", "/service/ensp/link/create", obj))
    elif cmd == "start":
        ensure_login()
        show("START", api("POST", "/service/ensp/device/batchStart",
                          {"deviceIds": [int(x) for x in sys.argv[3:]], "sandboxId": int(sys.argv[2])}))
    elif cmd == "stop":
        ensure_login()
        show("STOP", api("POST", "/service/ensp/device/batchStop",
                         {"deviceIds": [int(x) for x in sys.argv[3:]], "sandboxId": int(sys.argv[2])}))
    elif cmd == "cli":
        ensure_login()
        stomp_cli(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
