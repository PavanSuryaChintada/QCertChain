"""Process management for `python -m scripts.demo up|down`: start the local demo stack DETACHED (it survives the
terminal or the session that started it), detect what already runs by command line (so nothing starts twice: a second
ingest would duplicate the CT intake), and stop exactly the demo processes (never the test chain on :8546).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / ".superpowers"
PIDS = LOGS / "pids"
PY = sys.executable
CHAIN = "http://127.0.0.1:8545"
WIN = os.name == "nt"

# name -> (command line, marker found in its command line when running)
WORKERS = {
    "ingest": ([PY, "-m", "services.ingest.stream"], "services.ingest.stream"),
    "triage": ([PY, "-m", "services.api.workers.triage_worker"], "services.api.workers.triage_worker"),
    "enrich": ([PY, "-m", "services.api.workers.enrich_worker"], "services.api.workers.enrich_worker"),
    "anchor": ([PY, "-m", "services.api.workers.anchor_worker"], "services.api.workers.anchor_worker"),
    # the public site's way in (spec 2026-10-09 §10): publishes the quick-tunnel URL; restarted, it publishes anew
    "tunnel": ([PY, "-m", "scripts.tunnel"], "scripts.tunnel"),
}
API = ([PY, "-m", "uvicorn", "services.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
       "services.api.main:app")
CONSOLE = ([PY, "-m", "scripts.e2e_stack", "--serve", str(ROOT / "apps/console/dist"), "5180"], "dist 5180")
HARDHAT = str(ROOT / "contracts/node_modules/hardhat/internal/cli/cli.js")
CHAIN_CMD = (["node", HARDHAT, "node", "--hostname", "127.0.0.1", "--port", "8545"], "--port 8545")
ORDER = ("api", "console", "ingest", "triage", "enrich", "anchor", "tunnel")
SUPERVISOR = ([PY, "-m", "scripts.demo", "watch"], "scripts.demo watch")


# ---- pure decisions (tested) ------------------------------------------------------------------------------------
def services_to_start(alive: dict[str, bool]) -> list[str]:
    return [s for s in ORDER if not alive.get(s, False)]


def chain_plan(chain_was_running: bool, contracts_deployed: bool) -> list[str]:
    """A fresh chain (or one without the contracts) has lost every anchor: deploy, then reset + publish. A running
    chain with the contracts keeps the demo's anchors: only warm."""
    return ["warm"] if chain_was_running and contracts_deployed else ["deploy", "reset"]


def write_pid(folder: Path, name: str, pid: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.pid").write_text(str(pid), encoding="utf-8")


def read_pid(folder: Path, name: str) -> int | None:
    f = folder / f"{name}.pid"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def alive_map(procs: list[tuple[int, str]]) -> dict[str, bool]:
    """Liveness by PROCESS, not by HTTP: a busy API that answers slowly is alive (restarting it would clash on its
    port). The console marker is its own folder + port, so the offline e2e console (dist-e2e, :4173) cannot mask it."""
    alive = {name: any(marker in cmd for _, cmd in procs) for name, (_, marker) in WORKERS.items()}
    alive["api"] = any(API[1] in cmd for _, cmd in procs)
    alive["console"] = any(CONSOLE[1] in cmd for _, cmd in procs)
    return alive


# ---- probes ------------------------------------------------------------------------------------------------------
def http_ok(url: str, timeout: float = 5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 - a probe: any failure means "not up"
        return False


def rpc(method: str, params: list, timeout: float = 5):
    req = urllib.request.Request(CHAIN, data=json.dumps({"jsonrpc": "2.0", "method": method, "params": params,
                                                          "id": 1}).encode(),
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("result")
    except Exception:  # noqa: BLE001
        return None


def chain_alive() -> bool:
    return rpc("eth_chainId", []) is not None


def contracts_deployed() -> bool:
    dep = json.loads((ROOT / "contracts/deployments/localhost.json").read_text(encoding="utf-8"))
    code = rpc("eth_getCode", [dep["CampaignRegistry"], "latest"])
    return bool(code) and code not in ("0x", "0x0")


def running_processes() -> list[tuple[int, str]]:
    """(pid, command line) of every python/node process."""
    if WIN:
        ps = ("Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='node.exe'\" | "
              "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
        rows = json.loads(out) if out.strip() else []
        rows = rows if isinstance(rows, list) else [rows]
        return [(r["ProcessId"], r.get("CommandLine") or "") for r in rows]
    out = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True).stdout
    return [(int(line.split(None, 1)[0]), line.split(None, 1)[1]) for line in out.splitlines() if line.strip()]


def matching(marker: str, procs=None) -> list[int]:
    procs = running_processes() if procs is None else procs
    me = os.getpid()
    return [pid for pid, cmd in procs if marker in cmd and pid != me]


# ---- start / stop -------------------------------------------------------------------------------------------------
def start_detached(name: str, cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> int:
    """Start a process that outlives this one (Windows: its own process group, no console, out of the parent's job
    when allowed; POSIX: a new session). Output goes to .superpowers/<name>.log."""
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / f"{name}.log", "a", encoding="utf-8")
    kw = dict(cwd=str(cwd), env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1", **(env or {})},
              stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, close_fds=True)
    if WIN:
        base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            p = subprocess.Popen(cmd, creationflags=base | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            p = subprocess.Popen(cmd, creationflags=base, **kw)
    else:
        p = subprocess.Popen(cmd, start_new_session=True, **kw)
    write_pid(PIDS, name, p.pid)
    return p.pid


def kill(pid: int) -> None:
    if WIN:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def wait_for(probe, seconds: float, label: str) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if probe():
            return True
        time.sleep(2)
    print(f"  {label} did not come up within {seconds:.0f} s (see .superpowers/{label}.log)")
    return False


def docker_up() -> bool:
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
        if WIN and desktop.exists():
            print("  starting Docker Desktop ...")
            subprocess.Popen([str(desktop)], creationflags=subprocess.DETACHED_PROCESS)
        if not wait_for(lambda: subprocess.run(["docker", "info"], capture_output=True).returncode == 0, 240,
                        "docker"):
            return False
    r = subprocess.run(["docker", "start", "qcertchain-redis-1", "qcertchain-certstream-1"], capture_output=True,
                       text=True)
    if r.returncode != 0:
        print(f"  docker start failed: {r.stderr.strip()[:200]}")
        return False
    return True


def deploy_contracts() -> bool:
    dep = ROOT / "contracts/deployments/localhost.json"
    before = dep.read_text(encoding="utf-8")
    r = subprocess.run(["node", HARDHAT, "run", "scripts/deploy.ts", "--network", "localhost"],
                       cwd=ROOT / "contracts", env={**os.environ, "CHAIN_RPC": CHAIN}, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  deploy failed: {r.stderr.strip()[-300:]}")
        return False
    after = json.loads(dep.read_text(encoding="utf-8"))
    old = json.loads(before)
    if {k: v for k, v in after.items() if k != "deployedAt"} == {k: v for k, v in old.items() if k != "deployedAt"}:
        dep.write_text(before, encoding="utf-8")  # same addresses: keep the committed file (no timestamp churn)
    return True


def build_console_if_missing() -> bool:
    if (ROOT / "apps/console/dist/index.html").exists():
        return True
    npm = shutil.which("npm") or "npm"
    print("  building the console for production ...")
    r = subprocess.run(f'"{npm}" run build', cwd=ROOT / "apps/console", shell=True,
                       env={**os.environ, "VITE_API_URL": "http://127.0.0.1:8000"})
    return r.returncode == 0


def up() -> list[str]:
    """Bring every demo process up; returns the chain plan ("warm" or "deploy"+"reset")."""
    print("docker (redis, certstream) ...")
    if not docker_up():
        raise SystemExit("Docker is not available: start Docker Desktop, then run this again.")
    was_running = chain_alive()
    if not was_running:
        print("demo chain :8545 ...")
        start_detached("hardhat_8545", CHAIN_CMD[0], cwd=ROOT / "contracts")
        if not wait_for(chain_alive, 120, "hardhat_8545"):
            raise SystemExit("the demo chain did not start")
    plan = chain_plan(was_running, contracts_deployed())
    if "deploy" in plan:
        print("deploying contracts ...")
        if not deploy_contracts():
            raise SystemExit("contract deployment failed")
    alive = alive_map([(pid, cmd) for pid, cmd in running_processes() if pid != os.getpid()])
    alive["api"] = alive["api"] or http_ok("http://127.0.0.1:8000/health")
    alive["console"] = alive["console"] or http_ok("http://127.0.0.1:5180/")
    for name in services_to_start(alive):
        if name == "console" and not build_console_if_missing():
            raise SystemExit("console build failed")
        cmd = API[0] if name == "api" else CONSOLE[0] if name == "console" else WORKERS[name][0]
        print(f"starting {name} ...")
        start_detached(name, cmd)
    if not wait_for(lambda: http_ok("http://127.0.0.1:8000/health"), 180, "api"):
        raise SystemExit("the API did not start")
    wait_for(lambda: http_ok("http://127.0.0.1:5180/"), 60, "console")
    if not matching(SUPERVISOR[1]):
        print("starting the supervisor (restarts any demo process that dies) ...")
        start_detached("watch", SUPERVISOR[0])
    return plan


def watch(interval: float = 15.0) -> None:
    """Supervisor: every `interval` seconds, restart any demo process that is gone. The chain is never restarted
    here: a new chain has lost every anchor, so that is reported for `demo up` (which redeploys and re-anchors)."""
    print(time.strftime("%H:%M:%S"), "supervising the demo stack", flush=True)
    while True:
        try:
            alive = alive_map([(pid, cmd) for pid, cmd in running_processes() if pid != os.getpid()])
            for name in services_to_start(alive):
                cmd = API[0] if name == "api" else CONSOLE[0] if name == "console" else WORKERS[name][0]
                print(time.strftime("%H:%M:%S"), f"{name} was not running: restarted", flush=True)
                start_detached(name, cmd)
            if not chain_alive():
                print(time.strftime("%H:%M:%S"), "demo chain :8545 is down: run `scripts.demo up`", flush=True)
        except Exception as e:  # noqa: BLE001 - the supervisor itself must never die
            print(time.strftime("%H:%M:%S"), f"supervisor: {type(e).__name__}: {e}", flush=True)
        time.sleep(interval)


def down() -> int:
    for pid in matching(SUPERVISOR[1]):  # first, or it would restart what is being stopped
        kill(pid)
    procs = running_processes()
    markers = [API[1], CONSOLE[1], CHAIN_CMD[1], *(m for _, m in WORKERS.values())]
    pids = sorted({pid for m in markers for pid in matching(m, procs)})
    for pid in pids:
        kill(pid)
    print(f"stopped {len(pids)} demo processes (the test chain on :8546 and Docker are left running)")
    return 0
