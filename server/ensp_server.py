"""eNSP Pro MCP server - coarse-grained, name-based tools.

Env: ENSP_BASE (default https://192.168.1.20:28443), ENSP_STATE (state file path).
State: current sandbox remembered in ENSP_STATE json; devices addressed by NAME.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from ensp_client import EnspClient

STATE_PATH = os.environ.get(
    "ENSP_STATE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))

TYPE_ALIASES = {
    "switch": "ENSP-LSW", "lsw": "ENSP-LSW", "s": "ENSP-LSW",
    "ce": "ENSP-CE",
    "router": "ENSP-AR", "ar": "ENSP-AR",
    "ne": "ENSP-NE",
    "ap": "ENSP-AP",
    "ac": "ENSP-AC",
    "usg": "ENSP-USG", "firewall": "ENSP-USG",
    "pc": "PC-CLIENT", "client": "PC-CLIENT",
    "sta": "PC-STA",
    "server": "PC-SERVER",
    "dual": "PC-DUAL",
    "cloud": "ENSP-CLOUD",
}

STATUS_TEXT = {0: "stopped", 1: "running(vm)", 2: "starting(vm-pending)",
               3: "error(vm-add)", 4: "running(container)", 5: "error(container-add)",
               6: "starting(container-pending)"}

mcp = FastMCP("ensp-pro", instructions=(
    "Automates a Huawei eNSP Pro standalone server (topology editing, device power, "
    "VRP console automation). Devices are addressed by NAME within the current sandbox. "
    "Typical flow: ensp_lab('wlan-lab') -> ensp_add_devices -> ensp_link -> ensp_power(start) "
    "-> ensp_wait -> ensp_cli."))

C = EnspClient(os.environ.get("ENSP_BASE", "https://192.168.1.20:28443"))


def _load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f)


def _current_sandbox(explicit=None):
    """Resolve sandbox name -> id; explicit name wins, else remembered, else the only one."""
    st = _load_state()
    rows = C.sandbox_list()
    if not rows:
        raise ValueError("no sandboxes exist; call ensp_lab(name) to create one")
    by_name = {r["name"]: r for r in rows}
    name = explicit or st.get("current_sandbox")
    if name not in by_name:
        if explicit:
            raise ValueError(f"sandbox '{explicit}' not found; existing: {list(by_name)}")
        if st.get("current_sandbox") and rows:
            name = rows[0]["name"]
        else:
            name = rows[0]["name"]
    row = by_name[name]
    st["current_sandbox"] = name
    _save_state(st)
    return row["id"], name, row


def _resolve_device(sid, name):
    data = C.sandbox_get(sid)
    for d in data.get("devices", []):
        if d["name"] == name:
            return d, data
    raise ValueError(f"device '{name}' not found; existing: "
                     f"{[d['name'] for d in data.get('devices', [])]}")


@mcp.tool()
def ensp_status() -> str:
    """Server identity, all sandboxes (id/name/status/usage), and the current sandbox."""
    u = C.whoami().get("data") or {}
    rows = C.sandbox_list()
    st = _load_state()
    lines = [f"user={u.get('username')} (admin project: {u.get('projectName')})",
             f"current sandbox: {st.get('current_sandbox', '<none>')}", "sandboxes:"]
    for r in rows:
        lines.append(f"  {r['name']} (id={r['id']}, status={r['status']}, "
                     f"devices={r.get('usedVms', 0)}/{r.get('maxVms', '?')})")
    return "\n".join(lines)


@mcp.tool()
def ensp_lab(name: str = "") -> str:
    """Switch to sandbox by name (created if missing) and set it current. No arg: show sandboxes."""
    if not name:
        return ensp_status()
    rows = C.sandbox_list()
    by_name = {r["name"]: r for r in rows}
    if name in by_name:
        row = by_name[name]
    else:
        j = C.sandbox_create(name)
        if j.get("code") != 0:
            return f"create failed: {j.get('message')} (code {j.get('code')})"
        row = j["data"]
    st = _load_state()
    st["current_sandbox"] = name
    _save_state(st)
    data = C.sandbox_get(row["id"])
    devs = [f"{d['name']}({STATUS_TEXT.get(d.get('status'), d.get('status'))})"
            for d in data.get("devices", [])]
    return (f"sandbox '{name}' id={row['id']} status={row['status']} selected. "
            f"devices: {', '.join(devs) if devs else '<empty>'}")


@mcp.tool()
def ensp_topology(sandbox: str = "") -> str:
    """Compact topology dump: devices with status + all links as A:if -- B:if."""
    sid, name, _ = _current_sandbox(sandbox or None)
    data = C.sandbox_get(sid)
    out = [f"sandbox '{name}' (id={sid}, topo status={data.get('status')})"]
    out.append("devices:")
    for d in data.get("devices", []):
        prog = d.get("progress") or d.get("deviceStartProgress")
        st = STATUS_TEXT.get(d.get("status"), d.get("status"))
        prog_s = f", boot={prog}%" if isinstance(prog, (int, float)) else ""
        out.append(f"  {d['name']} (id={d['id']}, "
                   f"{d.get('deviceType', {}).get('displayName', '?')}, {st}{prog_s})")
    by_id = {d["id"]: d["name"] for d in data.get("devices", [])}
    if_map = {i["id"]: i["name"] for d in data.get("devices", []) for i in d.get("deviceIfs", [])}
    out.append("links:")
    for l in data.get("links", []):
        a = f"{by_id.get(l.get('leftDeviceId'), '?')}:{if_map.get(l.get('leftIfId'), '?')}"
        b = f"{by_id.get(l.get('rightDeviceId'), '?')}:{if_map.get(l.get('rightIfId'), '?')}"
        out.append(f"  {a} -- {b} (linkId={l.get('id')})")
    if not data.get("links"):
        out.append("  <none>")
    return "\n".join(out)


@mcp.tool()
def ensp_add_devices(devices: list, sandbox: str = "") -> str:
    """Create devices. items: "NAME:TYPE" strings (TYPE alias like LSW/AC/AP/STA/AR/CE/PC/SERVER/CLOUD) or {name,type,x,y}. x,y in [-0.5,0.5] canvas position (optional)."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    tpls = {t["name"]: t for t in C.device_types(sid)}
    results = []
    for idx, item in enumerate(devices):
        if isinstance(item, str):
            if ":" not in item:
                results.append(f"{item}: ERROR need NAME:TYPE")
                continue
            dname, tname = item.split(":", 1)
            x, y = -0.3 + 0.18 * (idx % 5), -0.2 + 0.2 * (idx // 5)
        else:
            dname, tname = item["name"], item["type"]
            x, y = item.get("x", -0.3 + 0.18 * (idx % 5)), item.get("y", -0.2 + 0.2 * (idx // 5))
        tpl_name = TYPE_ALIASES.get(tname.strip().lower(), tname.strip().upper())
        if tpl_name not in tpls:
            results.append(f"{dname}: ERROR unknown type '{tname}' ({list(tpls)})")
            continue
        j = C.device_create(sid, dname.strip(), tpl_name, x, y)
        if j.get("code") == 0:
            dev = (j.get("data") or [{}])[0]
            results.append(f"{dname}: created id={dev.get('id')} as {tpl_name}")
        else:
            results.append(f"{dname}: ERROR {j.get('message')} (code {j.get('code')})")
    return "\n".join(results)


@mcp.tool()
def ensp_link(links: list, sandbox: str = "") -> str:
    """Create links. items: [devA, ifA, devB, ifB] with interface names like GE1/0/1."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    data = C.sandbox_get(sid)
    by_name = {d["name"]: d for d in data.get("devices", [])}
    results = []
    for item in links:
        a, ia, b, ib = item
        try:
            da, db = by_name[a], by_name[b]
            ifa = next((i["id"] for i in da.get("deviceIfs", []) if i["name"] == ia), None)
            ifb = next((i["id"] for i in db.get("deviceIfs", []) if i["name"] == ib), None)
            if not ifa or not ifb:
                raise ValueError(f"interface not found ({ia}/{ib})")
            used = {l.get("leftIfId") for l in data.get("links", [])} | \
                   {l.get("rightIfId") for l in data.get("links", [])}
            if ifa in used or ifb in used:
                raise ValueError("interface already linked")
            j = C.link_create(sid, da["id"], ifa, db["id"], ifb)
            if j.get("code") == 0:
                results.append(f"{a}:{ia} -- {b}:{ib} OK")
                data = C.sandbox_get(sid)
                by_name = {d["name"]: d for d in data.get("devices", [])}
            else:
                results.append(f"{a}:{ia} -- {b}:{ib} ERROR {j.get('message')}")
        except Exception as e:
            results.append(f"{a}:{ia} -- {b}:{ib} ERROR {e}")
    return "\n".join(results)


@mcp.tool()
def ensp_power(action: str, devices: list, sandbox: str = "") -> str:
    """Power control. action: start|stop. devices: device names. Returns immediately; use ensp_wait to poll boot."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    data = C.sandbox_get(sid)
    by_name = {d["name"]: d for d in data.get("devices", [])}
    ids = []
    out = []
    for n in devices:
        if n in by_name:
            ids.append(by_name[n]["id"])
            out.append(f"{n}(id={by_name[n]['id']})")
        else:
            out.append(f"{n}: NOT FOUND")
    if ids:
        fn = C.device_start if action == "start" else C.device_stop
        j = fn(sid, ids)
        if j.get("code") != 0:
            return f"{action} failed: {j.get('message')}"
    return f"{action} issued for: {', '.join(out)}"


@mcp.tool()
def ensp_remove(devices: list, sandbox: str = "") -> str:
    """Delete devices by name (their links go with them)."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    data = C.sandbox_get(sid)
    by_name = {d["name"]: d for d in data.get("devices", [])}
    ids, out = [], []
    for n in devices:
        if n in by_name:
            ids.append(by_name[n]["id"])
            out.append(n)
    if not ids:
        return "nothing to delete"
    j = C.device_delete(sid, ids)
    if j.get("code") != 0:
        return f"delete failed: {j.get('message')}"
    return f"deleted: {', '.join(out)}"


@mcp.tool()
def ensp_wait(devices: list = None, sandbox: str = "", timeout: int = 100) -> str:
    """Poll until devices finish booting (max ~110s per call; re-call if still starting). No devices = all."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    end = time.time() + min(timeout, 110)
    target = set(devices) if devices else None
    snap = {}
    while time.time() < end:
        data = C.sandbox_get(sid)
        snap = {}
        for d in data.get("devices", []):
            if target and d["name"] not in target:
                continue
            snap[d["name"]] = (d.get("status"), d.get("progress") or d.get("deviceStartProgress"))
        if snap and all(s in (1, 4) for s, _ in snap.values()):
            break
        time.sleep(8)
    lines = [f"{n}: {STATUS_TEXT.get(s, s)}" + (f" boot={p}%" if isinstance(p, (int, float)) and s not in (1, 4) else "")
             for n, (s, p) in snap.items()]
    all_ready = bool(snap) and all(s in (1, 4) for s, _ in snap.values())
    return ("\n".join(lines) + f"\n{'ALL READY' if all_ready else 'still working - re-call ensp_wait'}")


@mcp.tool()
def ensp_cli(device: str, commands: list, sandbox: str = "",
             quiet: float = 2.0, timeout: float = 60.0) -> str:
    """Open the device console (auto-handles first-login password) and run commands one by one.
    Returns the combined transcript. One call per device; batch your command lines."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    dev, data = _resolve_device(sid, device)
    dtype = dev.get("deviceType", {}).get("name", "")
    C.console_open(sid, dev["id"], dtype)
    parts = []
    for cmd in commands:
        out = C.console_command(sid, dev["id"], cmd, quiet=quiet, timeout=timeout)
        out = out.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        parts.append(f"### {cmd}\n{out.strip()}")
    return "\n\n".join(parts)


@mcp.tool()
def ensp_console(device: str, sandbox: str = "", send: str = "",
                 seconds: float = 4.0) -> str:
    """Raw console access: optionally SEND text verbatim (no auto newline), then read the stream for `seconds`."""
    sid, sname, _ = _current_sandbox(sandbox or None)
    dev, _ = _resolve_device(sid, device)
    dtype = dev.get("deviceType", {}).get("name", "")
    C.console_open(sid, dev["id"], dtype)
    if send:
        C.console_send(sid, dev["id"], send)
    out = C.console_read_until_quiet(sid, dev["id"], quiet=min(2.0, seconds), timeout=max(seconds, 3.0))
    return out.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


if __name__ == "__main__":
    mcp.run(transport="stdio")
