import signal
import os
import json
import subprocess
import time
import stat
import fnmatch
import fcntl
from pathlib import Path

ROOT = Path("/var/lib/federation-repair")
EX = ROOT / "exchange"


def write_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def command(args, cwd=None, timeout=120):
    p = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:] or "Command failed")
    return p.stdout


def snapshot(root, limit):
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Invalid workspace")
    out = {}
    total = 0

    def fail(e):
        raise e

    for base, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in dirs + files:
            p = Path(base) / name
            s = p.lstat()
            if stat.S_ISLNK(s.st_mode):
                raise RuntimeError("Symlink rejected")
            if p.is_dir():
                continue
            if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                raise RuntimeError("Special file/hard link rejected")
            total += s.st_size
            if total > limit:
                raise RuntimeError("Workspace too large")
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def allowed(name, c):
    low = name.lower()
    if any(x in (".git", ".github", ".hermes") for x in low.split("/")):
        return False
    if any(fnmatch.fnmatch(low, g) for g in c["deny_globs"]):
        return False
    return (
        any(low.startswith(p.lower().rstrip("/") + "/") for p in c["allow_prefixes"])
        and Path(low).suffix in c["allow_extensions"]
    )


def main():
    cfg = json.loads(Path("/etc/federation-repair/worker.json").read_text())
    with (EX / "outbox" / "lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        for path in sorted((EX / "inbox").glob("*.json")):
            job = json.loads(path.read_text())
            jid = job["id"]
            if not jid or any(c not in "0123456789abcdef-" for c in jid):
                raise RuntimeError("Invalid job ID")
            done = EX / "outbox" / (jid + ".json")
            claim = EX / "outbox" / (jid + ".started")
            if done.exists() or claim.exists() or time.time() - job["created"] > 180:
                continue
            workspace = Path(job["workspace"])
            if (
                workspace.parent.resolve() != (EX / "workspaces").resolve()
                or workspace.is_symlink()
            ):
                raise RuntimeError("Invalid workspace")
            claim.write_text(str(time.time()))
            prompt = EX / "outbox" / (jid + "-task.txt")
            prompt.write_text(job["prompt"])
            env = os.environ.copy()
            for key in list(env):
                if key.startswith(("GH_", "GITHUB_")):
                    env.pop(key)
            code = 125
            with (EX / "outbox" / (jid + ".log")).open("w") as log:
                try:
                    p = subprocess.Popen(
                        cfg["hermes_command"]
                        + [
                            "chat",
                            "--base-url",
                            "http://192.168.178.90:11434/v1",
                            "--api-key",
                            "ollama",
                            "--model",
                            "qwen3.5:9b",
                            "--toolsets",
                            "terminal",
                            "--max-turns",
                            "30",
                            "--query-file",
                            str(prompt),
                        ],
                        cwd=workspace,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        code = p.wait(timeout=min(job["timeout"], cfg["max_timeout"]))
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
                        p.wait(timeout=20)
                        code = 124
                except Exception as error:
                    log.write(str(error))
            write_json(done, {"id": jid, "exit_code": code})
            break


if __name__ == "__main__":
    main()
