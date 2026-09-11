"""Runs learner code in a separate Python process with bounded resources.

What this does
  * fresh subprocess, `python -I -S -B` (isolated: no env PYTHON*, no user
    site, no site-packages, no script dir on sys.path)
  * stdin closed or fed from a fixed string; stdout/stderr capped in size
  * wall-clock timeout, then the process tree is killed
  * memory cap: a Windows Job Object (ProcessMemoryLimit + kill-on-close),
    or RLIMIT_AS on POSIX
  * runs in an empty temp directory that is deleted afterwards
  * a minimal environment (no inherited variables)

What this does NOT do — read this before trusting it with anything
  * It does not block network access or reads of other files on this machine.
    The learner's own code runs as the learner's own user. That is acceptable
    here because the only code that runs is code *you* typed, on *your*
    machine, against curated exercises. It is not a sandbox for untrusted
    code from other people. For that, use a container (CodeLock's judge is
    one example) or an OS-level sandbox.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

DEFAULT_TIMEOUT = 5.0
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
OUTPUT_CAP = 20_000  # characters kept from each stream

_HARNESS = textwrap.dedent(
    r'''
    import io, json, sys, traceback, contextlib
    spec = json.load(open("_spec.json", encoding="utf-8"))
    src = open("learner.py", encoding="utf-8").read()
    ns = {"__name__": "learner"}
    captured = io.StringIO()
    result = {"load_error": None, "load_output": "", "tests": []}
    try:
        with contextlib.redirect_stdout(captured):
            exec(compile(src, "learner.py", "exec"), ns)
    except BaseException as e:  # noqa: BLE001 - report everything
        result["load_error"] = "".join(traceback.format_exception_only(type(e), e)).strip()
    result["load_output"] = captured.getvalue()[:2000]
    if result["load_error"] is None:
        for t in spec["tests"]:
            entry = {"call": t.get("label") or "", "ok": False, "got": None, "error": None}
            try:
                fn = ns.get(t["fn"])
                if fn is None or not callable(fn):
                    raise NameError(f"no function named {t['fn']!r} was defined")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    got = fn(*t.get("args", []), **t.get("kwargs", {}))
                entry["got"] = repr(got)
                entry["printed"] = buf.getvalue()[:500]
                entry["ok"] = repr(got) == t["expect_repr"]
            except BaseException as e:  # noqa: BLE001
                entry["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()
            result["tests"].append(entry)
    sys.stdout.write("\n@@RESULT@@" + json.dumps(result))
    '''
)


def _friendly_error(stderr: str) -> str:
    """Last line of a traceback is the part a beginner needs first."""
    lines = [ln for ln in stderr.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    # Include the offending line number of the learner's file when available.
    import re
    for ln in reversed(lines):
        m = re.search(r'learner\.py", line (\d+)', ln)
        if m:
            return f"{last}  (line {m.group(1)})"
    return last


def _spawn(args: list[str], cwd: str, stdin_text: str | None, timeout: float) -> dict:
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if os.name == "nt":
        # SystemRoot is needed for the CRT to start at all on Windows.
        env["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
    else:
        env["PATH"] = "/usr/bin:/bin"

    popen_kwargs: dict = dict(
        cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        def _limit():
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
                resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
            except Exception:  # noqa: BLE001 - best effort
                pass
        popen_kwargs["preexec_fn"] = _limit

    proc = subprocess.Popen(args, **popen_kwargs)
    job = _assign_job(proc) if os.name == "nt" else None
    timed_out = False
    try:
        out, err = proc.communicate(input=stdin_text or "", timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=2)
        except Exception:  # noqa: BLE001
            out, err = "", ""
    finally:
        if job is not None:
            _close_job(job)
    return {
        "stdout": (out or "")[:OUTPUT_CAP],
        "stderr": (err or "")[:OUTPUT_CAP],
        "exit": proc.returncode,
        "timed_out": timed_out,
    }


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            proc.kill()
    except Exception:  # noqa: BLE001
        pass


# ---- Windows Job Object: memory cap + kill everything when we close it ----
def _assign_job(proc):
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
        JobObjectExtendedLimitInformation = 9

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = MEMORY_LIMIT_BYTES
        ok = k32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            k32.CloseHandle(job)
            return None
        handle = int(proc._handle)  # noqa: SLF001 - Popen exposes no public accessor
        if not k32.AssignProcessToJobObject(job, handle):
            k32.CloseHandle(job)
            return None
        return job
    except Exception:  # noqa: BLE001 - limits are best effort, never fatal
        return None


def _close_job(job) -> None:
    try:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(job)
    except Exception:  # noqa: BLE001
        pass


# ---- public API ---------------------------------------------------------
def run_program(code: str, stdin_text: str = "", timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Run `code` as a script. Returns stdout/stderr/exit/timed_out/error."""
    tmp = tempfile.mkdtemp(prefix="ss-run-")
    try:
        with open(os.path.join(tmp, "learner.py"), "w", encoding="utf-8") as f:
            f.write(code)
        res = _spawn([sys.executable, "-I", "-S", "-B", "learner.py"], tmp, stdin_text, timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res["error"] = _friendly_error(res["stderr"]) if res["exit"] != 0 or res["timed_out"] else ""
    if res["timed_out"]:
        res["error"] = f"Stopped after {timeout:g}s — is there a loop that never ends?"
    return res


def run_function_tests(code: str, tests: list[dict], timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Load `code`, then call functions per `tests`.

    Each test: {"fn": name, "args": [...], "expect": value, "label": "f(1, 2)"}
    Comparison is by repr(), which is strict but explainable to a beginner.
    """
    spec = {"tests": []}
    for t in tests:
        spec["tests"].append({
            "fn": t["fn"], "args": t.get("args", []), "kwargs": t.get("kwargs", {}),
            "expect_repr": repr(t["expect"]),
            "label": t.get("label") or f"{t['fn']}({', '.join(repr(a) for a in t.get('args', []))})",
        })
    tmp = tempfile.mkdtemp(prefix="ss-fn-")
    try:
        with open(os.path.join(tmp, "learner.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(tmp, "_spec.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f)
        with open(os.path.join(tmp, "_harness.py"), "w", encoding="utf-8") as f:
            f.write(_HARNESS)
        res = _spawn([sys.executable, "-I", "-S", "-B", "_harness.py"], tmp, "", timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out = {"ok": False, "tests": [], "error": "", "timed_out": res["timed_out"]}
    if res["timed_out"]:
        out["error"] = f"Stopped after {timeout:g}s — is there a loop that never ends?"
        return out
    marker = "\n@@RESULT@@"
    if marker not in res["stdout"]:
        out["error"] = _friendly_error(res["stderr"]) or "The program did not finish normally."
        return out
    payload = json.loads(res["stdout"].split(marker, 1)[1])
    if payload["load_error"]:
        out["error"] = payload["load_error"]
        return out
    for i, t in enumerate(payload["tests"]):
        exp = spec["tests"][i]["expect_repr"]
        out["tests"].append({
            "label": t["call"], "ok": t["ok"], "expected": exp,
            "got": t["got"], "error": t["error"], "printed": t.get("printed", ""),
        })
    out["ok"] = bool(out["tests"]) and all(t["ok"] for t in out["tests"])
    return out
