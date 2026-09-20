"""eNSP Pro automation client: REST + STOMP-over-SockJS device console.

Protocol (validated live against V100R003C10SPC101 standalone):
  GET  /api/login?service={base}/home  -> establishes admin session cookie (no password)
  REST envelope: {"code": 0, "message":..., "data":...}; 50010005/50070014 = session lost
  SockJS WS  {base}/web.socket/{server}/{session}/websocket
  STOMP destinations:
    SUB  /user/topic/console/message/{sandboxId}/{deviceId}   output stream
    SEND /app/console/connect|message|heartbeat|close/{sandboxId}/{deviceId}
  First console login on VRP devices: "Please configure the login password" ->
  set password -> Confirm -> prompt. Later sessions: no password on console 0.
"""
import json
import os
import re
import ssl
import threading
import time
import urllib3
import websocket

urllib3.disable_warnings()
import requests

CONSOLE_PW = "Admin@123"
PC_TYPES = {"PC-CLIENT", "PC-SERVER", "PC-STA", "PC-DUAL"}
SESSION_LOST_CODES = {50010005, 50070014}


def _sockjs_escape(s):
    return json.dumps(s)


class EnspClient:
    def __init__(self, base="https://192.168.1.20:28443"):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.verify = False
        self.s.headers["Accept-Language"] = "zh"
        self._ws = None
        self._ws_lock = threading.RLock()
        self._consoles = {}   # device_id -> {"dest": str, "buf": str, "ready": bool}
        self._cookie_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "state.cookies.json")

    # ---------- session ----------
    # Server enforces a single admin session: a browser login invalidates ours and
    # vice versa. Persist cookies so an MCP restart reuses the live session instead
    # of logging in again and kicking whoever holds the console.
    def _load_cookies(self):
        try:
            with open(self._cookie_path, encoding="utf-8") as f:
                data = json.load(f)
            for c in data.get("cookies", []):
                self.s.cookies.set(c["name"], c["value"], domain=c.get("domain"),
                                   path=c.get("path", "/"))
        except Exception:
            pass

    def _save_cookies(self):
        try:
            cookies = [{"name": c.name, "value": c.value, "domain": c.domain,
                        "path": c.path} for c in self.s.cookies]
            with open(self._cookie_path, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies}, f)
        except Exception:
            pass

    def _probe_ok(self):
        # /api/keepalive returns code 0 even for a half-invalidated session, so
        # probe with getUserInfo and require a non-empty data payload.
        try:
            r = self.s.get(self.base + "/api/getUserInfo", timeout=15)
            if r.status_code != 200:
                return False
            j = r.json()
            return j.get("code") == 0 and bool(j.get("data"))
        except Exception:
            return False

    def ensure_session(self):
        if not self.s.cookies:
            self._load_cookies()
        if self.s.cookies and self._probe_ok():
            return
        self.s.cookies.clear()
        self.s.get(self.base + "/api/login?service=" + self.base + "/home",
                   allow_redirects=True, timeout=30)
        self._save_cookies()

    def whoami(self):
        self.ensure_session()
        return self.s.get(self.base + "/api/getUserInfo", timeout=30).json()

    def keepalive(self):
        self.ensure_session()
        return self.s.get(self.base + "/api/keepalive", timeout=30).json()

    # ---------- sandbox / device REST ----------
    def sandbox_list(self):
        self.ensure_session()
        r = self.s.post(self.base + "/service/ensp/sandbox/getByPage",
                        json={"currentPage": 1, "pageSize": 50, "projectId": 1, "type": 0},
                        timeout=30).json()
        return r.get("data") or []

    def sandbox_create(self, name, max_vms=50):
        body = {"id": "", "name": name, "isPublic": 0, "maxVms": max_vms,
                "keepTime": 0, "type": 0, "projectId": 1}
        return self.s.post(self.base + "/service/ensp/sandbox/create", json=body,
                           timeout=60).json()

    def sandbox_get(self, sid):
        self.ensure_session()
        return self.s.get(self.base + f"/service/ensp/sandbox/getOneSandbox?sandboxId={sid}",
                          timeout=30).json().get("data") or {}

    def device_types(self, sid):
        self.ensure_session()
        return (self.s.get(self.base + f"/service/ensp/device-type/all?sandboxId={sid}",
                           timeout=30).json().get("data") or {}).get("devices") or []

    def device_create(self, sid, name, type_name, x=0.0, y=0.0):
        tpl = next(t for t in self.device_types(sid) if t["name"] == type_name)
        dev = {"deviceType": tpl, "deviceTypeId": tpl["id"], "name": name,
               "sandboxId": sid,
               "devicePosition": {"positionX": x, "positionY": y},
               "namePosition": {"positionX": x, "positionY": y + 0.08}}
        return self.s.post(self.base + "/service/ensp/device/batchCreate",
                           json={"devices": [dev], "sandboxId": sid}, timeout=60).json()

    def device_delete(self, sid, device_ids):
        return self.s.post(self.base + "/service/ensp/device/batchDelete",
                           json={"deviceIds": device_ids, "sandboxId": sid}, timeout=60).json()

    def device_start(self, sid, device_ids):
        return self.s.post(self.base + "/service/ensp/device/batchStart",
                           json={"deviceIds": device_ids, "sandboxId": sid}, timeout=60).json()

    def device_stop(self, sid, device_ids):
        return self.s.post(self.base + "/service/ensp/device/batchStop",
                           json={"deviceIds": device_ids, "sandboxId": sid}, timeout=60).json()

    def link_create(self, sid, left_id, left_if_id, right_id, right_if_id):
        body = {"leftDeviceId": left_id, "leftIfId": left_if_id,
                "rightDeviceId": right_id, "rightIfId": right_if_id,
                "linkTypeId": 1, "sandboxId": sid}
        return self.s.post(self.base + "/service/ensp/link/create", json=body, timeout=60).json()

    def device_status_map(self, sid):
        data = self.sandbox_get(sid)
        return {d["id"]: d for d in data.get("devices", [])}, data

    # ---------- STOMP / SockJS ----------
    def _ensure_ws(self):
        # The server tears down the whole websocket after a device console
        # session ends, so drop dead sockets and reconnect transparently.
        if self._ws is not None and not getattr(self._ws, "connected", False):
            self._ws = None
        if self._ws is None:
            self.ensure_session()
            cookie = "; ".join(f"{c.name}={c.value}" for c in self.s.cookies)
            self._ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
            self._ws.connect(
                f"{self.base.replace('https:', 'wss:')}/web.socket/000/mcp{int(time.time()*1000)}/websocket",
                header=[f"Cookie: {cookie}"], origin=self.base, timeout=10)
        return self._ws

    def _send_stomp(self, cmd, headers, body=""):
        ws = self._ensure_ws()
        lines = [cmd] + [f"{k}:{v}" for k, v in headers.items()]
        if body:
            lines.append(f"content-length:{len(body.encode())}")
        ws.send(json.dumps(["\n".join(lines) + "\n\n" + body + "\x00"]))

    def _drain(self, seconds):
        end = time.time() + seconds
        ws = self._ensure_ws()
        while time.time() < end:
            ws.settimeout(max(0.05, end - time.time()))
            try:
                data = ws.recv()
            except Exception:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8", "replace")
            if not data.startswith("a"):
                continue
            for item in json.loads(data[1:]):
                head, _, body2 = item.partition("\n\n")
                lines = head.split("\n")
                if lines[0].strip() != "MESSAGE":
                    continue
                dest = next((l.split(":", 1)[1] for l in lines[1:]
                             if l.startswith("destination:")), None)
                for st in self._consoles.values():
                    if st["dest"] == dest:
                        st["buf"] += body2

    # ---------- console ----------
    def console_open(self, sid, device_id, device_type=None):
        with self._ws_lock:
            st = self._consoles.get(device_id)
            if st and st["ready"]:
                return
            cid = f"{sid}/{device_id}"
            self._consoles[device_id] = {"dest": f"/user/topic/console/message/{cid}",
                                         "buf": "", "ready": True}
            self._send_stomp("CONNECT", {"accept-version": "1.2", "heart-beat": "30000,30000"})
            self._drain(4)
            self._send_stomp("SUBSCRIBE", {"destination": self._consoles[device_id]["dest"],
                                           "id": f"sub-{device_id}"})
            self._send_stomp("SEND", {"destination": f"/app/console/connect/{cid}"})
            self._drain(3)
            self._console_bootstrap(sid, device_id, device_type)

    def _console_bootstrap(self, sid, device_id, device_type=None):
        """Drive the console to a usable state: first-login password set, reconnect
        password check, ENTER gate, VRP screen length. Loop until a VRP prompt shows."""
        is_pc = (device_type or "").upper() in PC_TYPES
        prompt_re = re.compile(r"<[\w.-]+>|\[[\w.-]+\]")
        for _ in range(6):
            out = self.console_read_until_quiet(sid, device_id, quiet=2.0, timeout=10)
            text = out.replace("\x00", "")
            if "Confirm Password" in text:
                self.console_send(sid, device_id, CONSOLE_PW + "\r")
                time.sleep(2)
                self._drain(3)
                continue
            if "Please configure the login password" in text or re.search(r"Password\s*:", text):
                self.console_send(sid, device_id, CONSOLE_PW + "\r")
                time.sleep(1)
                self._drain(3)
                continue
            if "Please Press ENTER" in text:
                self.console_send(sid, device_id, "\r")
                continue
            if is_pc:
                return
            if prompt_re.search(text):
                self.console_command(sid, device_id, "screen-length 0 temporary")
                return
            self.console_send(sid, device_id, "\r")

    def console_send(self, sid, device_id, text):
        with self._ws_lock:
            st = self._consoles.get(device_id)
            if not st:
                self.console_open(sid, device_id)
            self._send_stomp("SEND", {"destination": f"/app/console/message/{sid}/{device_id}"},
                             text)

    def console_read_until_quiet(self, sid, device_id, quiet=2.0, timeout=30.0):
        with self._ws_lock:
            st = self._consoles.setdefault(
                device_id, {"dest": f"/user/topic/console/message/{sid}/{device_id}",
                            "buf": "", "ready": False})
            start = time.time()
            last_len, last_change = -1, time.time()
            while time.time() - start < timeout:
                self._drain(0.4)
                if len(st["buf"]) != last_len:
                    last_len, last_change = len(st["buf"]), time.time()
                elif time.time() - last_change >= quiet:
                    break
            out, st["buf"] = st["buf"], ""
            return out

    def console_command(self, sid, device_id, cmd, quiet=2.0, timeout=45.0):
        st = self._consoles.get(device_id)
        if st:
            st["buf"] = ""
        self.console_send(sid, device_id, cmd + "\r")
        return self.console_read_until_quiet(sid, device_id, quiet=quiet, timeout=timeout)

    def console_close(self, sid, device_id):
        with self._ws_lock:
            try:
                self._send_stomp("SEND",
                                 {"destination": f"/app/console/close/{sid}/{device_id}"})
            except Exception:
                pass
            self._consoles.pop(device_id, None)

    def close(self):
        with self._ws_lock:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None
            self._consoles.clear()
