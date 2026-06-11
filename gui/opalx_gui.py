#!/usr/bin/env python3
"""
Local OPALX regression-test GUI.

This is intentionally dependency-free: it serves one modern web interface and
wraps the existing NightlyBuildX scripts without replacing their workflow.
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import errno
import shutil
import subprocess
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKSPACE = ROOT / "workspace"
OPALX_CHECKOUT = WORKSPACE / "opalx"
REGTESTS_CHECKOUT = WORKSPACE / "regression-tests-x"
BUILD_ROOT = WORKSPACE / "build"
CONFIG_DIR = SCRIPTS / "config"
RUN_TESTS = SCRIPTS / "run_tests"
DEFAULT_PUBLISH_DIR = Path.home() / "opalx-html"
HISTORY_FILE = ROOT / "gui" / "run-history.json"
STATE_FILE = ROOT / "gui" / "ui-state.json"
DEFAULT_REFERENCE_SOURCE = REGTESTS_CHECKOUT / "RegressionTests"


@dataclass
class RunRecord:
    id: str
    started_at: str
    status: str
    command: list[str]
    cwd: str
    opalx_source_dir: str
    opalx_build_dir: str
    opalx_exe_path: str
    opalx_branch: str
    regtests_branch: str
    config: str
    publish_dir: str
    tests: list[str] = field(default_factory=list)
    returncode: int | None = None
    finished_at: str | None = None


RUNS: dict[str, RunRecord] = {}
RUN_LOGS: dict[str, queue.Queue[str | None]] = {}
RUN_LOCK = threading.Lock()


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, body: str, content_type: str = "text/html") -> None:
    encoded = body.encode()
    handler.send_response(200)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def run_git(args: list[str], cwd: Path) -> list[str]:
    try:
        output = subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def sanitize_branch(name: str) -> str:
    name = name.strip()
    if name.startswith("origin/"):
        return name[len("origin/") :]
    return name


def expand_path_text(path_text: str) -> Path:
    text = (path_text or "").strip()
    home = str(Path.home())
    if text == "$HOME":
        text = home
    elif text.startswith("$HOME" + os.sep):
        text = home + text[len("$HOME") :]
    elif text == "~":
        text = home
    elif text.startswith("~" + os.sep):
        text = home + text[1:]
    return Path(text).expanduser().resolve()


def display_path(path: Path) -> str:
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text


def list_remote_branches(repo: Path) -> list[str]:
    branches = set()
    for line in run_git(["branch", "-r", "--format=%(refname:short)"], repo):
        if line.endswith("/HEAD"):
            continue
        branch = sanitize_branch(line)
        if branch and branch != "origin":
            branches.add(branch)
    return sorted(branches)


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    top_level = run_git(["rev-parse", "--show-toplevel"], path)
    if not top_level:
        return False
    return Path(top_level[0]).resolve() == path.resolve()


def list_local_branches(repo: Path) -> list[str]:
    if is_git_repo(repo):
        branches = run_git(["branch", "--format=%(refname:short)"], repo)
        current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
        names = set(branches)
        names.update(current)
        return sorted(name for name in names if name and name != "HEAD")
    return []


def current_branch(repo: Path) -> str:
    if not is_git_repo(repo):
        return ""
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    return branch[0] if branch and branch[0] != "HEAD" else ""


def is_opalx_source(repo: Path) -> bool:
    return (
        is_git_repo(repo)
        and (repo / "CMakeLists.txt").is_file()
        and (repo / "src" / "OpalConfigure").is_dir()
        and (repo / "src" / "Main.cpp").is_file()
    )


def is_opalx_exe_dir(path: Path) -> bool:
    opalx = path / "opalx"
    return path.is_dir() and opalx.is_file() and os.access(opalx, os.X_OK)


def is_opalx_build_dir(path: Path) -> bool:
    return path.is_dir() and (path / "CTestTestfile.cmake").is_file() and is_opalx_exe_dir(path / "src")


def build_source_dir(build_dir: Path) -> Path | None:
    cache = build_dir / "CMakeCache.txt"
    if not cache.exists():
        return None
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
            return Path(line.split("=", 1)[1])
    return None


def build_branch(build_dir: Path) -> str:
    source_dir = build_source_dir(build_dir)
    if source_dir is None:
        return ""
    return current_branch(source_dir)


def matching_build_dir(source_dir: Path, build_dirs: list[str]) -> str:
    source = source_dir.resolve()
    matches = []
    for build_dir_text in build_dirs:
        build_dir = Path(build_dir_text).resolve()
        build_source = build_source_dir(build_dir)
        if build_source and build_source.resolve() == source:
            matches.append(build_dir)
    preferred = source / "build"
    for build_dir in matches:
        if build_dir == preferred:
            return str(build_dir)
    return str(matches[0]) if matches else ""


def discover_opalx_sources() -> list[str]:
    candidates = [
        WORKSPACE / "opalx",
        WORKSPACE / "opalx" / "src",
        WORKSPACE / "master" / "src",
    ]
    if WORKSPACE.exists():
        candidates.extend(path / "src" for path in WORKSPACE.iterdir() if path.is_dir())
    git_dir = Path.home() / "git"
    if git_dir.exists():
        candidates.extend(path for path in git_dir.iterdir() if path.is_dir())
        candidates.extend(path / "src" for path in git_dir.iterdir() if path.is_dir())
    seen = set()
    sources = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_opalx_source(resolved):
            sources.append(str(resolved))
    return sources


def discover_opalx_build_dirs() -> list[str]:
    candidates = [
        WORKSPACE / "build",
        WORKSPACE / "opalx" / "cpu-serial" / "build",
        WORKSPACE / "opalx",
        Path.home() / "git" / "opalx" / "build",
        Path.home() / "git" / "opalx-beambeam" / "build_openmp",
    ]
    for root in [WORKSPACE, Path.home() / "git"]:
        if root.exists():
            candidates.extend(path.parent for path in root.glob("**/src/opalx") if path.is_file())
    seen = set()
    dirs = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_opalx_build_dir(resolved):
            dirs.append(str(resolved))
    return dirs


def list_workspace_branches() -> list[str]:
    return list_local_branches(OPALX_CHECKOUT)


def list_regtests_branches() -> list[str]:
    return list_local_branches(REGTESTS_CHECKOUT)


def list_configs() -> list[str]:
    if not CONFIG_DIR.exists():
        return []
    return sorted(path.name for path in CONFIG_DIR.glob("*.conf"))


def valid_test_dir(path: Path) -> bool:
    test = path.name
    return (
        path.is_dir()
        and not test.startswith(".")
        and (path / f"{test}.in").is_file()
        and (path / "reference" / f"{test}.stat").is_file()
        and not (path / "disabled").exists()
    )


def list_tests(branch: str) -> list[str]:
    test_base = REGTESTS_CHECKOUT / "RegressionTests"
    if not test_base.exists():
        test_base = WORKSPACE / branch / "tests" / "RegressionTests"
    if not test_base.exists():
        return []
    return sorted(path.name for path in test_base.iterdir() if valid_test_dir(path))


def parse_config(config_name: str) -> dict[str, str]:
    path = CONFIG_DIR / config_name
    data = {"architecture": "cpu-serial", "branch": "master", "regtests_branch": "master"}
    if not path.exists():
        return data
    pattern = re.compile(r'^\s*(branch|regtests_branch|architecture)=["\']?([^"\']+)["\']?')
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            data[match.group(1)] = match.group(2)
    return data


def list_results(publish_dir: Path = DEFAULT_PUBLISH_DIR) -> dict[str, Any]:
    results: dict[str, Any] = {"publish_dir": str(publish_dir), "branches": []}
    overview = publish_dir / "overview"
    if not overview.exists():
        return results
    for branch_dir in sorted(path for path in overview.iterdir() if path.is_dir()):
        branch = {"name": branch_dir.name, "architectures": []}
        for arch_dir in sorted(path for path in branch_dir.iterdir() if path.is_dir()):
            branch["architectures"].append(
                {
                    "name": arch_dir.name,
                    "overview": str(arch_dir / "index.html") if (arch_dir / "index.html").exists() else "",
                }
            )
        index = branch_dir / "index.html"
        if index.exists():
            branch["landing"] = str(index)
        results["branches"].append(branch)
    return results


def command_value(command: list[str], flag: str) -> str:
    try:
        index = command.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(command):
        return ""
    return command[index + 1]


def run_architecture(record: dict[str, Any]) -> str:
    config = record.get("config") or "debug-cpu.conf"
    return parse_config(config).get("architecture", "cpu-serial")


def run_publish_branch(record: dict[str, Any]) -> str:
    command = record.get("command") or []
    branch = command_value(command, "--opalx-branch")
    if branch:
        return branch
    config = record.get("config") or "debug-cpu.conf"
    return parse_config(config).get("branch", "master")


def run_plot_timestamp(record: dict[str, Any]) -> str:
    started = record.get("started_at", "")
    if len(started) < 16:
        return ""
    return started[:16].replace(" ", "_").replace(":", "-")


def list_run_plots(run_id: str) -> dict[str, Any]:
    history = load_history()
    record = next((item for item in history if item.get("id") == run_id), None)
    if not record:
        return {"run_id": run_id, "plots": []}

    candidates = run_result_candidates(record, "plots")
    tests = record.get("tests") or []
    plots = []
    seen = set()
    for plot_dir in candidates:
        if not plot_dir.exists():
            continue
        for path in sorted(plot_dir.glob("*.png")):
            if tests and not any(path.name.startswith(f"{test}_") for test in tests):
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            metric = path.stem
            for test in tests:
                prefix = f"{test}_"
                if metric.startswith(prefix):
                    metric = metric[len(prefix):]
                    break
            plots.append(
                {
                    "path": resolved,
                    "name": path.name,
                    "metric": metric,
                    "test": next((test for test in tests if path.name.startswith(f"{test}_")), ""),
                }
            )
    return {"run_id": run_id, "timestamp": run_plot_timestamp(record), "plots": plots}


def run_result_candidates(record: dict[str, Any], kind: str) -> list[Path]:
    timestamp = run_plot_timestamp(record)
    architecture = run_architecture(record)
    branch = run_publish_branch(record)
    publish_dir = Path(record.get("publish_dir") or DEFAULT_PUBLISH_DIR)
    if kind == "plots":
        candidates = [publish_dir / "regressionTests" / branch / architecture / f"plots_{timestamp}"]
        candidates.extend(publish_dir.glob(f"regressionTests/*/{architecture}/plots_{timestamp}"))
        return candidates
    candidates = [publish_dir / "regressionTests" / branch / architecture / f"results_{timestamp}.xml"]
    candidates.extend(publish_dir.glob(f"regressionTests/*/{architecture}/results_{timestamp}.xml"))
    return candidates


def run_summary(run_id: str) -> dict[str, Any]:
    history = load_history()
    record = next((item for item in history if item.get("id") == run_id), None)
    if not record:
        return {"run_id": run_id, "simulations": [], "counts": {"passed": 0, "failed": 0, "broken": 0}}
    for xml_path in run_result_candidates(record, "xml"):
        if not xml_path.exists():
            continue
        root = ET.parse(xml_path).getroot()
        simulations = []
        counts = {"passed": 0, "failed": 0, "broken": 0}
        for sim in root.findall("Simulation"):
            tests = []
            sim_counts = {"passed": 0, "failed": 0, "broken": 0}
            for test in sim.findall("Test"):
                state = (test.findtext("state") or "broken").strip()
                if state not in sim_counts:
                    state = "broken"
                sim_counts[state] += 1
                counts[state] += 1
                tests.append(
                    {
                        "var": test.get("var", ""),
                        "mode": test.get("mode", ""),
                        "state": state,
                        "eps": test.findtext("eps") or "",
                        "delta": test.findtext("delta") or "",
                    }
                )
            simulations.append(
                {
                    "name": sim.get("name", ""),
                    "description": sim.get("description", ""),
                    "counts": sim_counts,
                    "tests": tests,
                }
            )
        return {"run_id": run_id, "path": str(xml_path), "counts": counts, "simulations": simulations}
    status = "passed" if record.get("returncode") == 0 else "failed"
    return {
        "run_id": run_id,
        "path": "",
        "counts": {"passed": 1 if status == "passed" else 0, "failed": 1 if status == "failed" else 0, "broken": 0},
        "simulations": [{"name": test, "description": "", "counts": {"passed": 1 if status == "passed" else 0, "failed": 1 if status == "failed" else 0, "broken": 0}, "tests": []} for test in (record.get("tests") or [])],
    }


def parse_stat_columns(statfile: Path) -> list[dict[str, str]]:
    if not statfile.exists():
        return []
    columns = []
    lines = statfile.read_text(errors="replace").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if "&column" in line:
            block = line
            while "&end" not in line and index + 1 < len(lines):
                index += 1
                line = lines[index]
                block += line
            name_match = re.search(r"name=([^,]+)", block)
            units_match = re.search(r"units=([^,]+)", block)
            if name_match:
                name = name_match.group(1).strip()
                if name not in ("t", "s"):
                    columns.append(
                        {
                            "name": name,
                            "units": units_match.group(1).strip() if units_match else "",
                        }
                    )
        if "&data" in line:
            break
        index += 1
    return columns


def reference_info(path_text: str) -> dict[str, Any]:
    test_dir = expand_path_text(path_text)
    input_files = sorted(test_dir.glob("*.in")) if test_dir.is_dir() else []
    simname = input_files[0].stem if len(input_files) == 1 else ""
    stat_candidates = []
    if simname:
        stat_candidates = [test_dir / f"{simname}.stat", test_dir / "reference" / f"{simname}.stat"]
    statfile = next((path for path in stat_candidates if path.exists()), None)
    return {
        "path": str(test_dir),
        "valid": test_dir.is_dir() and len(input_files) == 1,
        "input_files": [path.name for path in input_files],
        "simname": simname,
        "statfile": str(statfile) if statfile else "",
        "columns": parse_stat_columns(statfile) if statfile else [],
        "rt_file": str(test_dir / f"{simname}.rt") if simname else "",
    }


def existing_rt_columns(test_dir: Path, simname: str) -> dict[str, str]:
    rt_file = test_dir / f"{simname}.rt"
    if not rt_file.exists():
        return {}
    selected = {}
    for line in rt_file.read_text(errors="replace").splitlines():
        match = re.search(r'^stat\s+"([^"]+)"\s+(last|avg)\b', line.strip())
        if match:
            selected[match.group(1)] = match.group(2)
    return selected


def run_make_reference(path_text: str, opalx_exe_path: str, ranks: int = 1) -> dict[str, Any]:
    test_dir = expand_path_text(path_text)
    info = reference_info(str(test_dir))
    if not info["valid"]:
        return {"returncode": 1, "output": "Directory must contain exactly one .in file.\n"}
    exe_dir = expand_path_text(opalx_exe_path)
    if not (exe_dir / "opalx").is_file():
        return {"returncode": 1, "output": f"Invalid OPALX executable directory: {exe_dir}\n"}
    env = os.environ.copy()
    env["OPALX_EXE_PATH"] = str(exe_dir)
    env["PATH"] = f"{REGTESTS_CHECKOUT / 'bin'}:{env.get('PATH', '')}"
    command = ["makeReference.sh", "--ranks", str(ranks)]
    process = subprocess.run(
        command,
        cwd=test_dir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {"returncode": process.returncode, "output": process.stdout}


def write_reference_rt(payload: dict[str, Any]) -> dict[str, Any]:
    test_dir = expand_path_text(payload.get("path", ""))
    info = reference_info(str(test_dir))
    if not info["valid"] or not info["simname"]:
        return {"ok": False, "error": "Directory must contain exactly one .in file."}
    columns = payload.get("columns") or []
    if not columns:
        return {"ok": False, "error": "Select at least one stat column."}
    normalized = []
    for column in columns:
        if isinstance(column, str):
            normalized.append({"name": column, "check": payload.get("check") or "last"})
        else:
            normalized.append({"name": column.get("name", ""), "check": column.get("check") or "last"})
    columns = [column for column in normalized if column["name"]]
    if not columns:
        return {"ok": False, "error": "Select at least one stat column."}
    if any(column["check"] not in ("last", "avg") for column in columns):
        return {"ok": False, "error": "Check must be last or avg."}
    tolerance = payload.get("tolerance") or "1E-9"
    description = (payload.get("description") or f"{info['simname']} reference").replace('"', "'")
    rt_path = test_dir / f"{info['simname']}.rt"
    lines = [f'"{description}"']
    width = max(len(column["name"]) for column in columns)
    for column in columns:
        name = column["name"]
        lines.append(f'stat "{name}"{" " * max(1, width - len(name) + 1)}{column["check"]} {tolerance}')
    rt_path.write_text("\n".join(lines) + "\n")
    return {"ok": True, "path": str(rt_path)}


def copy_reference_to_repo(path_text: str) -> dict[str, Any]:
    source_dir = expand_path_text(path_text)
    info = reference_info(str(source_dir))
    if not info["valid"]:
        return {"ok": False, "error": "Directory must contain exactly one .in file."}
    target_root = REGTESTS_CHECKOUT / "RegressionTests"
    target_root.mkdir(parents=True, exist_ok=True)
    target_dir = target_root / source_dir.name
    if source_dir.resolve() == target_dir.resolve():
        return {
            "ok": True,
            "path": str(target_dir),
            "message": "Already in regression-tests-x repository.",
        }
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
    return {
        "ok": True,
        "path": str(target_dir),
        "message": f"Copied to {display_path(target_dir)}",
    }


def list_reference_rt_files(root_text: str = "") -> list[dict[str, str]]:
    root = expand_path_text(root_text) if root_text else DEFAULT_REFERENCE_SOURCE
    if not root.exists():
        return []
    files = []
    rt_files = [root] if root.is_file() and root.suffix == ".rt" else sorted(root.rglob("*.rt"))
    for rt_file in rt_files:
        test_dir = rt_file.parent
        info = reference_info(str(test_dir))
        if not info["valid"]:
            continue
        files.append(
            {
                "name": display_path(rt_file),
                "path": str(test_dir),
                "rt_file": str(rt_file),
            }
        )
    return files


def load_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []
    for record in history:
        if record.get("opalx_branch") == "external executable" and record.get("opalx_build_dir"):
            branch = build_branch(Path(record["opalx_build_dir"]))
            if branch:
                record["opalx_branch"] = branch
    return history


def save_history(record: RunRecord) -> None:
    history = load_history()
    history.insert(0, asdict(record))
    HISTORY_FILE.write_text(json.dumps(history[:100], indent=2) + "\n")


def load_ui_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_ui_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def should_show_console_line(line: str, command: list[str]) -> bool:
    if "--reg-tests" not in command:
        return True
    stripped = line.strip()
    if not stripped:
        return False
    test_args = []
    if "--" in command:
        test_args = command[command.index("--") + 1 :]
    else:
        test_args = [item for item in command if item and not item.startswith("-")][1:]
    keep_prefixes = (
        "$ ",
        "Using existing OPALX",
        "Updating ",
        "Working directory ",
        "Running the following regression tests:",
        "Running regression tests",
        "Running regression test",
        "Running test:",
        "Starting ",
        "Comparing ",
        "Process exited ",
        "ERROR:",
        "WARNING:",
        "FAILED",
        "PASSED",
        "Broken:",
        "Failed:",
        "Passed:",
        "Total:",
    )
    if stripped.startswith(keep_prefixes):
        return True
    if line.startswith(("    ", "\t")):
        return True
    if stripped in test_args:
        return True
    if " - unknown test!" in stripped:
        return True
    if stripped.startswith(("ok ", "not ok ")):
        return True
    return False


def build_command(payload: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    opalx_source_dir = payload.get("opalx_source_dir") or ""
    opalx_build_dir = payload.get("opalx_build_dir") or ""
    opalx_exe_path = payload.get("opalx_exe_path") or ""
    opalx_branch = payload.get("opalx_branch") or (current_branch(Path(opalx_source_dir)) if opalx_source_dir else "") or "master"
    regtests_branch = payload.get("regtests_branch") or "master"
    config = payload.get("config") or "debug-cpu.conf"
    publish_dir = str(expand_path_text(payload.get("publish_dir") or str(DEFAULT_PUBLISH_DIR)))
    tests = payload.get("tests") or []

    command = [
        "bash",
        str(RUN_TESTS),
        "--config",
        str(CONFIG_DIR / config),
        "--regtests-branch",
        regtests_branch,
        "--publish-dir",
        publish_dir,
    ]
    external_build = bool(opalx_build_dir or opalx_exe_path)
    if opalx_build_dir:
        command.extend(["--opalx-build-dir", opalx_build_dir])
    if opalx_exe_path:
        command.extend(["--opalx-exe-path", opalx_exe_path])
    if not external_build:
        command.extend(["--opalx-branch", opalx_branch])

    if payload.get("no_gpl", True):
        command.append("--no-gpl")
    if not payload.get("unit_tests", True):
        command.append("--no-unit-tests")
    if not payload.get("reg_tests", True):
        command.append("--no-reg-tests")
    if external_build:
        if payload.get("unit_tests") and not payload.get("reg_tests", True):
            command.append("--unit-tests")
        if payload.get("reg_tests", True):
            command.append("--reg-tests")
    elif payload.get("force"):
        command.append("--force")
    else:
        if payload.get("compile"):
            command.append("--compile")
        if payload.get("unit_tests", True):
            command.append("--unit-tests")
        if payload.get("reg_tests", True):
            command.append("--reg-tests")
    if payload.get("only_generate_web_page"):
        command.append("--only-generate-web-page")

    command.extend(tests)
    meta = {
        "opalx_source_dir": opalx_source_dir,
        "opalx_build_dir": opalx_build_dir,
        "opalx_exe_path": opalx_exe_path,
        "opalx_branch": opalx_branch if opalx_branch != "external executable" else (build_branch(Path(opalx_build_dir)) if opalx_build_dir else opalx_branch),
        "regtests_branch": regtests_branch,
        "config": config,
        "publish_dir": publish_dir,
    }
    return command, meta


def start_run(payload: dict[str, Any]) -> RunRecord:
    command, meta = build_command(payload)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    record = RunRecord(
        id=run_id,
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        status="running",
        command=command,
        cwd=str(WORKSPACE),
        tests=payload.get("tests") or [],
        **meta,
    )
    log_queue: queue.Queue[str | None] = queue.Queue()

    with RUN_LOCK:
        RUNS[run_id] = record
        RUN_LOGS[run_id] = log_queue

    def worker() -> None:
        log_queue.put("$ " + " ".join(command) + "\n\n")
        process = subprocess.Popen(
            command,
            cwd=WORKSPACE,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            if should_show_console_line(line, command):
                log_queue.put(line)
        returncode = process.wait()
        record.returncode = returncode
        record.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        record.status = "ok" if returncode == 0 else "failed"
        save_history(record)
        log_queue.put(f"\nProcess exited with code {returncode}\n")
        log_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()
    return record


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OPALX Lab</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-2: #eef3f7;
      --ink: #18212f;
      --muted: #647184;
      --line: #d9e0e8;
      --accent: #0f766e;
      --accent-2: #2563eb;
      --danger: #b42318;
      --shadow: 0 14px 38px rgba(21, 32, 43, .10);
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(246, 247, 249, .92);
      backdrop-filter: blur(14px);
    }
    h1 { margin: 0; font-size: 20px; font-weight: 720; letter-spacing: 0; }
    .brand-line {
      display: flex;
      align-items: baseline;
      gap: 14px;
      flex-wrap: wrap;
    }
    .header-links {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      font-size: 13px;
    }
    .header-links a {
      color: var(--accent-2);
      font-weight: 720;
    }
    .subtle { color: var(--muted); font-size: 13px; }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px 24px 28px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .left, .right { display: grid; gap: 18px; align-content: start; }
    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 16px 10px;
      border-bottom: 1px solid var(--line);
    }
    h2 { margin: 0; font-size: 14px; text-transform: uppercase; color: #3b4657; letter-spacing: .08em; }
    .panel-body { padding: 16px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { display: grid; gap: 6px; font-size: 12px; color: var(--muted); font-weight: 640; }
    select, input[type="text"] {
      width: 100%;
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
    }
    .toggles {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 14px;
    }
    .toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      font-size: 13px;
      color: var(--ink);
    }
    button {
      height: 40px;
      border: 0;
      border-radius: 6px;
      padding: 0 14px;
      background: var(--accent);
      color: white;
      font-weight: 720;
      font: inherit;
      cursor: pointer;
    }
    button.secondary { background: #dfe7ef; color: #18212f; }
    button:disabled { opacity: .55; cursor: default; }
    .actions { display: flex; gap: 10px; margin-top: 14px; }
    .tests {
      display: grid;
      gap: 6px;
      max-height: 280px;
      overflow: auto;
      padding-right: 4px;
    }
    .test-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      font-size: 13px;
    }
    .command {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #101820;
      color: #d6f4e8;
      border-radius: 8px;
      padding: 14px;
      min-height: 84px;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .console {
      height: 460px;
      overflow: auto;
      margin: 0;
      background: #0e131a;
      color: #dbe7f3;
      border-radius: 8px;
      padding: 14px;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }
    .branches, .results {
      display: grid;
      gap: 8px;
    }
    .item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      background: var(--panel-2);
      color: #354153;
      font-size: 12px;
      font-weight: 700;
    }
    .status-icon {
      display: inline-grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      font-size: 17px;
      font-weight: 800;
      line-height: 1;
    }
    .status-ok { background: #dcfce7; color: #15803d; }
    .status-failed { background: #fee2e2; color: #b42318; }
    .status-running { background: #dbeafe; color: #1d4ed8; }
    .wheel {
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr) 42px;
      align-items: center;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .wheel button {
      width: 42px;
      padding: 0;
      background: #e7edf3;
      color: var(--ink);
      font-size: 22px;
    }
    .wheel-core {
      display: grid;
      gap: 8px;
      justify-items: center;
      text-align: center;
      min-width: 0;
    }
    .wheel-ring {
      width: 86px;
      height: 86px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at center, #fff 0 36%, transparent 37%),
        conic-gradient(#0f766e 0 22%, #2563eb 22% 48%, #d9e0e8 48% 100%);
      border: 1px solid var(--line);
    }
    .wheel-ring .status-icon { background: white; box-shadow: 0 2px 10px rgba(21, 32, 43, .12); }
    .run-strip {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding: 6px 2px 8px;
      margin-top: 8px;
    }
    .run-chip {
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fbfcfd;
      color: var(--ink);
      height: 30px;
      padding: 0 10px;
      font-size: 12px;
      font-weight: 800;
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .run-chip.active {
      border-color: var(--accent-2);
      box-shadow: 0 0 0 2px rgba(37, 99, 235, .14);
    }
    .run-chip.ok { background: #dcfce7; color: #15803d; }
    .run-chip.failed { background: #fee2e2; color: #b42318; }
    .run-chip.running { background: #dbeafe; color: #1d4ed8; }
    .run-overview {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .overview-kpis {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .overview-kpi {
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
    }
    .overview-kpi strong {
      display: block;
      font-size: 18px;
    }
    .test-state {
      display: inline-flex;
      align-items: center;
      height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
    }
    .test-state.passed { background: #dcfce7; color: #15803d; }
    .test-state.failed { background: #fef3c7; color: #b45309; }
    .test-state.broken { background: #fee2e2; color: #b42318; }
    .error-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .error-table th, .error-table td {
      padding: 7px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    .error-table th:last-child,
    .error-table td:last-child {
      text-align: right;
      white-space: nowrap;
    }
    .error-table th {
      color: var(--muted);
      font-weight: 800;
      background: #fbfcfd;
    }
    .error-table td {
      overflow-wrap: anywhere;
    }
    .tabs {
      display: inline-flex;
      gap: 4px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #eef3f7;
    }
    .tab {
      height: 30px;
      padding: 0 10px;
      border-radius: 5px;
      background: transparent;
      color: var(--muted);
      font-size: 13px;
    }
    .tab.active { background: #fff; color: var(--ink); box-shadow: 0 1px 4px rgba(21, 32, 43, .08); }
    .mode-tabs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      padding: 6px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef3f7;
    }
    .mode-tabs button {
      background: transparent;
      color: var(--muted);
    }
    .mode-tabs button.active {
      background: #fff;
      color: var(--ink);
      box-shadow: 0 1px 4px rgba(21, 32, 43, .08);
    }
    .stat-column {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 92px;
      gap: 8px;
      align-items: center;
      width: 100%;
    }
    .stat-column select {
      height: 30px;
      min-height: 30px;
      padding: 0 8px;
    }
    .hidden { display: none; }
    .plot-stage {
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr) 42px;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .plot-stage button {
      width: 42px;
      padding: 0;
      background: #e7edf3;
      color: var(--ink);
      font-size: 22px;
    }
    .plot-frame {
      display: grid;
      gap: 8px;
      justify-items: center;
      min-width: 0;
    }
    .plot-frame img {
      max-width: 100%;
      max-height: 460px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    .columns {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 6px;
      max-height: 220px;
      overflow: auto;
      padding-right: 4px;
    }
    a { color: var(--accent-2); text-decoration: none; font-weight: 680; }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; padding: 14px; }
      header { padding: 14px; align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="brand-line">
        <h1>OPALX Lab</h1>
        <div class="header-links">
          <a target="_blank" href="https://github.com/OPALX-project/NightlyBuildX">NightlyBuildX</a>
          <a target="_blank" href="https://github.com/OPALX-project/regression-tests-x">regression-tests-x</a>
        </div>
      </div>
      <div class="subtle">Builds, regression runs, reference creation, and published results</div>
    </div>
    <div class="subtle" id="root"></div>
  </header>

  <main>
    <div class="left">
      <div class="mode-tabs">
        <button type="button" id="runModeBtn" class="active">Run Builder</button>
        <button type="button" id="refModeBtn">Reference Builder</button>
      </div>

      <section id="runBuilderPanel">
        <div class="panel-head"><h2>Run Builder</h2><span class="pill" id="testCount">0 tests</span></div>
        <div class="panel-body">
          <div class="grid">
            <label>Source directory<select id="opalxSource"></select></label>
            <label>Detected branch<input id="opalxBranch" type="text" readonly /></label>
            <label>Regression branch<select id="regBranch"></select></label>
            <label>Config<select id="config"></select></label>
            <label>Publish directory<input id="publishDir" type="text" /></label>
          </div>
          <div class="toggles">
            <label class="toggle"><input type="checkbox" id="noGpl" checked /> Python plots</label>
            <label class="toggle"><input type="checkbox" id="force" /> Force all</label>
            <label class="toggle"><input type="checkbox" id="compile" /> Compile</label>
            <label class="toggle"><input type="checkbox" id="unitTests" checked /> Unit tests</label>
            <label class="toggle"><input type="checkbox" id="regTests" checked /> Regression tests</label>
            <label class="toggle"><input type="checkbox" id="webOnly" /> HTML only</label>
          </div>
          <div class="actions">
            <button id="runBtn">Run</button>
            <button class="secondary" id="refreshBtn">Refresh</button>
          </div>
        </div>
      </section>

      <section id="testsPanel">
        <div class="panel-head"><h2>Tests</h2><button class="secondary" id="clearTests">All</button></div>
        <div class="panel-body"><div class="tests" id="tests"></div></div>
      </section>

      <section id="referenceBuilderPanel" class="hidden">
        <div class="panel-head"><h2>Reference Builder</h2><span class="pill" id="refStatus">idle</span></div>
        <div class="panel-body">
          <div class="grid">
            <label>Regression test source<input id="refSourceRoot" type="text" /></label>
            <label>Regression test .rt file<select id="refDir"></select></label>
            <label>Description<input id="refDescription" type="text" /></label>
            <label>Tolerance<input id="refTolerance" type="text" value="1E-9" /></label>
          </div>
          <div class="actions">
            <button class="secondary" id="refSearchRt">Search .rt files</button>
            <button class="secondary" id="refScan">Scan</button>
            <button class="secondary" id="refRun">Run Reference</button>
            <button id="refWrite">Write .rt</button>
            <button class="secondary" id="refCopyRepo">Copy to repo</button>
          </div>
          <div class="subtle" id="refExeInfo" style="margin-top:10px"></div>
          <div class="subtle" id="refInfo" style="margin:12px 0 8px"></div>
          <div class="columns" id="refColumns"></div>
        </div>
      </section>

      <section>
        <div class="panel-head"><h2>Regression Errors</h2><span class="pill" id="errorRun">none</span></div>
        <div class="panel-body" id="errorTable"><div class="subtle">Select a regression run in the wheel.</div></div>
      </section>
    </div>

    <div class="right">
      <section>
        <div class="panel-head"><h2>Command</h2><span class="pill" id="status">idle</span></div>
        <div class="panel-body"><pre class="command" id="command"></pre></div>
      </section>

      <section>
        <div class="panel-head"><h2>Live Console</h2></div>
        <div class="panel-body"><pre class="console" id="console"></pre></div>
      </section>

      <section>
        <div class="panel-head"><h2>Results Browser</h2></div>
        <div class="panel-body"><div class="results" id="results"></div></div>
      </section>
    </div>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    const state = { tests: [], selectedTests: new Set(), meta: null };
    let refColumns = [];

    function displayPath(path) {
      if (!state.meta || !state.meta.home || !path) return path || "";
      if (path === state.meta.home) return "~";
      return path.startsWith(`${state.meta.home}/`) ? `~${path.slice(state.meta.home.length)}` : path;
    }

    async function api(path, options) {
      const res = await fetch(path, options);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }

    function optionList(select, values, selected) {
      select.innerHTML = values.map(item => {
        const value = typeof item === "string" ? item : item.value;
        const label = typeof item === "string" ? item : item.label;
        const selectedAttr = value === selected ? "selected" : "";
        return `<option value="${value}" ${selectedAttr}>${label}</option>`;
      }).join("");
    }

    function payload() {
      const selected = state.meta.opalx_choices.find(item => item.value === $("opalxSource").value);
      const sourcePath = selected && selected.kind === "source" ? selected.value : "";
      const buildPath = selected && selected.kind === "build"
        ? selected.value
        : (selected && selected.kind === "source" && selected.build_dir && !$("compile").checked ? selected.build_dir : "");
      return {
        opalx_source_dir: buildPath ? "" : sourcePath,
        opalx_build_dir: buildPath,
        opalx_branch: selected && selected.branch ? selected.branch : $("opalxBranch").value,
        regtests_branch: $("regBranch").value,
        config: $("config").value,
        publish_dir: $("publishDir").value,
        no_gpl: $("noGpl").checked,
        force: $("force").checked,
        compile: $("compile").checked,
        unit_tests: $("unitTests").checked,
        reg_tests: $("regTests").checked,
        only_generate_web_page: $("webOnly").checked,
        tests: [...state.selectedTests],
      };
    }

    function selectedOpalxExePath() {
      const selected = state.meta.opalx_choices.find(item => item.value === $("opalxSource").value);
      if (selected && selected.exe_dir) return selected.exe_dir;
      const data = payload();
      if (data.opalx_build_dir) return `${data.opalx_build_dir}/src`;
      const config = state.meta.config_details && state.meta.config_details[data.config] ? state.meta.config_details[data.config] : {};
      const architecture = config.architecture || "cpu-serial";
      return `${state.meta.build_root}/${architecture}/src`;
    }

    function updateReferenceExeLabel() {
      const label = $("refExeInfo");
      if (label) label.textContent = `Executable: ${displayPath(`${selectedOpalxExePath()}/opalx`)}`;
    }

    function setMode(mode) {
      const reference = mode === "reference";
      $("runBuilderPanel").classList.toggle("hidden", reference);
      $("testsPanel").classList.toggle("hidden", reference);
      $("referenceBuilderPanel").classList.toggle("hidden", !reference);
      $("runModeBtn").classList.toggle("active", !reference);
      $("refModeBtn").classList.toggle("active", reference);
      updateReferenceExeLabel();
      saveUiStateSoon();
    }

    async function refreshCommand() {
      const data = await api("/api/command", {
        method: "POST",
        body: JSON.stringify(payload()),
      });
      $("command").textContent = data.command.join(" ");
    }

    async function refreshTests() {
      state.tests = await api("/api/tests");
      state.selectedTests.clear();
      renderTests();
      refreshCommand();
    }

    async function refreshSourceBranch() {
      const selected = state.meta.opalx_choices.find(item => item.value === $("opalxSource").value);
      if (selected && selected.kind === "build") {
        $("opalxBranch").value = selected.branch || "";
        $("compile").checked = false;
      } else {
        const sourcePath = $("opalxSource").value;
        const data = await api(`/api/source-branch?path=${encodeURIComponent(sourcePath)}`);
        $("opalxBranch").value = data.branch || "";
      }
      await refreshCommand();
      updateReferenceExeLabel();
    }

    function renderTests() {
      $("testCount").textContent = `${state.tests.length} tests`;
      $("tests").innerHTML = state.tests.map(test => `
        <label class="test-row">
          <span>${test}</span>
          <input type="checkbox" data-test="${test}">
        </label>
      `).join("") || `<div class="subtle">No tests found for this branch yet.</div>`;
      document.querySelectorAll("[data-test]").forEach(box => {
        if (restoreState && restoreState.selectedTests && restoreState.selectedTests.includes(box.dataset.test)) {
          box.checked = true;
          state.selectedTests.add(box.dataset.test);
        }
        box.addEventListener("change", () => {
          if (box.checked) state.selectedTests.add(box.dataset.test);
          else state.selectedTests.delete(box.dataset.test);
          refreshCommand();
          saveUiStateSoon();
        });
      });
    }

    function renderReferenceColumns(columns, selected = []) {
      refColumns = columns || [];
      const selectedMap = new Map();
      if (Array.isArray(selected)) {
        selected.forEach(item => selectedMap.set(item, "last"));
      } else {
        Object.entries(selected || {}).forEach(([name, check]) => selectedMap.set(name, check || "last"));
      }
      $("refColumns").innerHTML = refColumns.map(column => `
        <label class="toggle">
          <input type="checkbox" data-ref-column="${column.name}" ${selectedMap.has(column.name) ? "checked" : ""} />
          <span class="stat-column">
            <span>${column.name}${column.units ? ` [${column.units}]` : ""}</span>
            <select data-ref-check="${column.name}">
              <option value="last" ${selectedMap.get(column.name) !== "avg" ? "selected" : ""}>last</option>
              <option value="avg" ${selectedMap.get(column.name) === "avg" ? "selected" : ""}>avg</option>
            </select>
          </span>
        </label>
      `).join("") || `<div class="subtle">No stat columns available yet.</div>`;
    }

    async function scanReference() {
      const refPath = $("refDir").value;
      const info = await api(`/api/reference/scan?path=${encodeURIComponent(refPath)}`);
      $("refStatus").textContent = info.valid ? "valid" : "invalid";
      $("refInfo").textContent = info.valid
        ? `${info.input_files[0]} | ${info.statfile ? displayPath(info.statfile) : "no stat file yet"}`
        : "Directory must contain exactly one .in file.";
      if (!$("refDescription").value && info.simname) $("refDescription").value = `${info.simname} reference`;
      renderReferenceColumns(info.columns, info.selected || []);
    }

    async function refreshReferenceRtFiles(selected = "") {
      const root = $("refSourceRoot").value || "$HOME";
      const data = await api(`/api/reference/rt-files?root=${encodeURIComponent(root)}`);
      const items = data.files || [];
      const nextSelected = selected || (items[0] ? items[0].path : "");
      optionList($("refDir"), items.map(item => ({ value: item.path, label: item.name })), nextSelected);
      $("refInfo").textContent = items.length
        ? `${items.length} .rt file${items.length === 1 ? "" : "s"} found under ${data.root_display || root}`
        : `No .rt files found under ${data.root_display || root}`;
      if ($("refDir").value) await scanReference();
    }

    async function runReference() {
      $("refStatus").textContent = "running";
      const result = await api("/api/reference/run", {
        method: "POST",
        body: JSON.stringify({
          path: $("refDir").value,
          opalx_exe_path: selectedOpalxExePath(),
          ranks: 1,
        }),
      });
      $("refStatus").textContent = result.returncode === 0 ? "ok" : "failed";
      $("console").textContent = result.output;
      await scanReference();
    }

    async function writeReferenceRt() {
      const selected = [...document.querySelectorAll("[data-ref-column]:checked")].map(box => {
        const check = document.querySelector(`[data-ref-check="${CSS.escape(box.dataset.refColumn)}"]`);
        return { name: box.dataset.refColumn, check: check ? check.value : "last" };
      });
      const result = await api("/api/reference/write-rt", {
        method: "POST",
        body: JSON.stringify({
          path: $("refDir").value,
          description: $("refDescription").value,
          tolerance: $("refTolerance").value,
          columns: selected,
        }),
      });
      $("refStatus").textContent = result.ok ? "rt written" : "failed";
      $("refInfo").textContent = result.path ? displayPath(result.path) : (result.error || "");
    }

    async function copyReferenceToRepo() {
      const result = await api("/api/reference/copy-to-repo", {
        method: "POST",
        body: JSON.stringify({ path: $("refDir").value }),
      });
      $("refStatus").textContent = result.ok ? "copied" : "failed";
      $("refInfo").textContent = result.message || (result.path ? displayPath(result.path) : (result.error || ""));
    }

    function fileUrl(path) {
      return `/file?path=${encodeURIComponent(path)}`;
    }

    let regressionWheelIndex = 0;
    let regressionTestIndex = 0;
    let plotIndex = 0;
    let resultsTab = "runs";
    let restoreState = null;
    let restoringState = false;
    let saveTimer = null;

    function currentUiState() {
      return {
        opalxSource: $("opalxSource").value,
        regBranch: $("regBranch").value,
        config: $("config").value,
        publishDir: $("publishDir").value,
        noGpl: $("noGpl").checked,
        force: $("force").checked,
        compile: $("compile").checked,
        unitTests: $("unitTests").checked,
        regTests: $("regTests").checked,
        webOnly: $("webOnly").checked,
        selectedTests: [...state.selectedTests],
        mode: $("referenceBuilderPanel").classList.contains("hidden") ? "run" : "reference",
        refSourceRoot: $("refSourceRoot").value,
        refDir: $("refDir").value,
        resultsTab,
        regressionWheelIndex,
        regressionTestIndex,
        plotIndex,
      };
    }

    function saveUiStateSoon() {
      if (restoringState) return;
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        api("/api/state", { method: "POST", body: JSON.stringify(currentUiState()) }).catch(() => {});
      }, 180);
    }

    function applySavedSelections() {
      if (!restoreState) return;
      const setValue = (id, value) => {
        if (value === undefined || value === null) return;
        const el = $(id);
        if (!el) return;
        if (el.tagName === "SELECT" && ![...el.options].some(option => option.value === value)) return;
        el.value = value;
      };
      const setChecked = (id, value) => {
        if (value === undefined || value === null) return;
        $(id).checked = Boolean(value);
      };
      setValue("opalxSource", restoreState.opalxSource);
      setValue("regBranch", restoreState.regBranch);
      setValue("config", restoreState.config);
      setValue("publishDir", restoreState.publishDir);
      setChecked("noGpl", restoreState.noGpl);
      setChecked("force", restoreState.force);
      setChecked("compile", restoreState.compile);
      setChecked("unitTests", restoreState.unitTests);
      setChecked("regTests", restoreState.regTests);
      setChecked("webOnly", restoreState.webOnly);
      setValue("refSourceRoot", restoreState.refSourceRoot);
      setValue("refDir", restoreState.refDir);
      resultsTab = restoreState.resultsTab || resultsTab;
      regressionWheelIndex = Number.isInteger(restoreState.regressionWheelIndex) ? restoreState.regressionWheelIndex : regressionWheelIndex;
      regressionTestIndex = Number.isInteger(restoreState.regressionTestIndex) ? restoreState.regressionTestIndex : regressionTestIndex;
      plotIndex = Number.isInteger(restoreState.plotIndex) ? restoreState.plotIndex : plotIndex;
      setMode(restoreState.mode || "run");
    }

    function iconFor(status) {
        if (status === "ok") return `<span class="status-icon status-ok" title="OK">✓</span>`;
        if (status === "running") return `<span class="status-icon status-running" title="Running">…</span>`;
        return `<span class="status-icon status-failed" title="Failed">!</span>`;
    }

    function isUnitRun(run) {
      return Array.isArray(run.command) && run.command.includes("--unit-tests") && !run.command.includes("--reg-tests");
    }

    function isRegressionRun(run) {
      return Array.isArray(run.command) && run.command.includes("--reg-tests");
    }

    function actionFor(run) {
      if (isUnitRun(run)) return "Unit tests";
      if (isRegressionRun(run) && run.tests && run.tests.length) return run.tests.join(", ");
      if (isRegressionRun(run)) return "Regression tests";
      if (run.tests && run.tests.length) return run.tests.join(", ");
      return "Run";
    }

    function compactRunLabel(run) {
      if (!run) return "none";
      if (isUnitRun(run)) return "unit";
      if (isRegressionRun(run) && run.tests && run.tests.length === 1) return run.tests[0];
      if (isRegressionRun(run) && run.tests && run.tests.length > 1) return `${run.tests.length} tests`;
      if (isRegressionRun(run)) return "regression";
      return "run";
    }

    function summarizedTestNames(tests) {
      if (!tests || !tests.length) return "all regression tests";
      if (tests.length <= 5) return tests.join(", ");
      return `${tests[0]}, ${tests[1]}, ... ${tests[tests.length - 2]}, ${tests[tests.length - 1]}`;
    }

    function renderRunRow(run, emptyText) {
      if (!run) return `<div class="subtle">${emptyText}</div>`;
      return `
        <div class="item">
          <div>
            <strong>${actionFor(run)}</strong>
            <div class="subtle">${run.finished_at || run.started_at}${run.returncode === null ? "" : ` | exit ${run.returncode}`}</div>
          </div>
          ${iconFor(run.status)}
        </div>`;
    }

    function selectedSimulation(summary) {
      const simulations = summary && summary.simulations ? summary.simulations : [];
      if (!simulations.length) return null;
      regressionTestIndex = ((regressionTestIndex % simulations.length) + simulations.length) % simulations.length;
      return simulations[regressionTestIndex];
    }

    function renderRegressionWheel(runs) {
      if (!runs.length) return `<div class="subtle">No regression runs recorded yet.</div>`;
      regressionWheelIndex = ((regressionWheelIndex % runs.length) + runs.length) % runs.length;
      const run = runs[regressionWheelIndex];
      return `
        <div class="wheel">
          <button type="button" id="regPrev" title="Previous regression run">‹</button>
          <div class="wheel-core">
            <div class="wheel-ring">${iconFor(run.status)}</div>
            <strong>${compactRunLabel(run)}</strong>
            <div class="subtle">${regressionWheelIndex + 1} / ${runs.length} runs | ${run.finished_at || run.started_at}${run.returncode === null ? "" : ` | exit ${run.returncode}`}</div>
            <div class="subtle">${summarizedTestNames(run.tests)}</div>
          </div>
          <button type="button" id="regNext" title="Next regression run">›</button>
        </div>`;
    }

    function renderRunStrip(runs) {
      if (runs.length < 2) return "";
      return `
        <div class="run-strip" aria-label="Regression run shortcuts">
          ${runs.map((run, index) => `
            <button type="button"
              class="run-chip ${run.status || "failed"} ${index === regressionWheelIndex ? "active" : ""}"
              data-run-index="${index}"
              title="${actionFor(run)} | ${run.finished_at || run.started_at}">
              ${compactRunLabel(run)}
            </button>
          `).join("")}
        </div>`;
    }

    async function renderRunOverview(run) {
      if (!run) return "";
      const data = await api(`/api/run-summary?run_id=${encodeURIComponent(run.id)}`);
      const counts = data.counts || { passed: 0, failed: 0, broken: 0 };
      const simulations = data.simulations || [];
      const testStrip = simulations.length > 1 ? `
        <div class="run-strip" aria-label="Regression tests in selected run">
          ${simulations.map((sim, index) => {
            const simCounts = sim.counts || {};
            const state = simCounts.broken ? "failed" : (simCounts.failed ? "failed" : "ok");
            return `<button type="button" class="run-chip ${state} ${index === regressionTestIndex ? "active" : ""}" data-test-index="${index}" title="${sim.name}">${sim.name}</button>`;
          }).join("")}
        </div>` : "";
      return `
        <div class="run-overview">
          ${testStrip}
          <div class="overview-kpis">
            <div class="overview-kpi"><strong>${counts.passed || 0}</strong><span class="subtle">passed</span></div>
            <div class="overview-kpi"><strong>${counts.failed || 0}</strong><span class="subtle">failed</span></div>
            <div class="overview-kpi"><strong>${counts.broken || 0}</strong><span class="subtle">broken</span></div>
          </div>
          <div class="subtle">${simulations.length} regression test${simulations.length === 1 ? "" : "s"} in this run</div>
          ${simulations.map(sim => {
            const simCounts = sim.counts || {};
            const state = simCounts.broken ? "broken" : (simCounts.failed ? "failed" : "passed");
            return `
              <div class="item">
                <div>
                  <strong>${sim.name || "Regression test"}</strong>
                  <div class="subtle">${sim.description || ""}</div>
                </div>
                <span class="test-state ${state}">${simCounts.passed || 0}/${(sim.tests || []).length || ((simCounts.passed || 0) + (simCounts.failed || 0) + (simCounts.broken || 0))}</span>
              </div>`;
          }).join("")}
        </div>`;
    }

    async function renderRegressionErrors(run) {
      const table = $("errorTable");
      const label = $("errorRun");
      if (!table || !label) return;
      if (!run) {
        label.textContent = "none";
        table.innerHTML = `<div class="subtle">No regression run selected.</div>`;
        return;
      }
      const data = await api(`/api/run-summary?run_id=${encodeURIComponent(run.id)}`);
      const selected = selectedSimulation(data);
      label.textContent = selected ? selected.name : compactRunLabel(run);
      const rows = [];
      (selected ? [selected] : (data.simulations || [])).forEach(sim => {
        (sim.tests || []).forEach(test => {
          if (test.state !== "passed") {
            rows.push({ sim: sim.name, ...test });
          }
        });
      });
      if (!rows.length) {
        table.innerHTML = `<div class="item"><span>No failed checks for ${compactRunLabel(run)}</span><span class="test-state passed">passed</span></div>`;
        return;
      }
      table.innerHTML = `
        <table class="error-table">
          <thead><tr><th>Test</th><th>Variable</th><th>Mode</th><th>Delta</th><th>Eps</th><th>State</th></tr></thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${row.sim || ""}</td>
                <td>${row.var || ""}</td>
                <td>${row.mode || ""}</td>
                <td>${row.delta || ""}</td>
                <td>${row.eps || ""}</td>
                <td><span class="test-state ${row.state}">${row.state}</span></td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    async function renderPlotSlider(run, selectedTest = "") {
      if (!run) return `<div class="subtle">No regression run selected.</div>`;
      const data = await api(`/api/plots?run_id=${encodeURIComponent(run.id)}`);
      const plots = selectedTest
        ? (data.plots || []).filter(plot => plot.test === selectedTest || plot.name.startsWith(`${selectedTest}_`))
        : (data.plots || []);
      if (!plots.length) return `<div class="subtle">No plots found for ${selectedTest || "this regression run"}.</div>`;
      plotIndex = ((plotIndex % plots.length) + plots.length) % plots.length;
      const plot = plots[plotIndex];
      return `
        <div class="plot-stage">
          <button type="button" id="plotPrev" title="Previous plot">‹</button>
          <div class="plot-frame">
            <img src="${fileUrl(plot.path)}" alt="${plot.name}">
            <strong>${plot.metric || plot.name}</strong>
            <div class="subtle">${plotIndex + 1} / ${plots.length}${plot.test ? ` | ${plot.test}` : ""}</div>
          </div>
          <button type="button" id="plotNext" title="Next plot">›</button>
        </div>`;
    }

    function renderPublishedResults(data) {
      return data.branches.map(branch => `
        <div class="item">
          <div>
            <strong>${branch.name}</strong>
            <div class="subtle">${branch.architectures.map(a => a.name).join(", ") || "No architectures"}</div>
          </div>
          <div>
            ${branch.landing ? `<a target="_blank" href="${fileUrl(branch.landing)}">Open</a>` : ""}
          </div>
        </div>
        ${branch.architectures.map(a => `
          <div class="item" style="margin-left:16px">
            <span>${a.name}</span>
            ${a.overview ? `<a target="_blank" href="${fileUrl(a.overview)}">Overview</a>` : ""}
          </div>
        `).join("")}
      `).join("") || `<div class="subtle">No published results found.</div>`;
    }

    async function renderResults() {
      const history = state.meta ? state.meta.history : [];
      const unitRuns = history.filter(isUnitRun);
      const regressionRuns = history.filter(isRegressionRun);
      regressionWheelIndex = regressionRuns.length ? ((regressionWheelIndex % regressionRuns.length) + regressionRuns.length) % regressionRuns.length : 0;
      const selectedRegressionRun = regressionRuns[regressionWheelIndex];
      const selectedRunSummary = selectedRegressionRun ? await api(`/api/run-summary?run_id=${encodeURIComponent(selectedRegressionRun.id)}`) : null;
      const selectedSim = selectedSimulation(selectedRunSummary);
      await renderRegressionErrors(selectedRegressionRun);
      $("results").innerHTML = `
        <div class="tabs">
          <button type="button" class="tab ${resultsTab === "runs" ? "active" : ""}" id="resultsRunsTab">Runs</button>
          <button type="button" class="tab ${resultsTab === "plots" ? "active" : ""}" id="resultsPlotsTab">Plots</button>
        </div>
        <div class="subtle" style="margin-bottom:8px">Latest unit test</div>
        ${renderRunRow(unitRuns[0], "No unit-test runs recorded yet.")}
        ${resultsTab === "runs" ? `<div class="subtle" style="margin:14px 0 8px">Regression wheel</div>${renderRegressionWheel(regressionRuns)}${renderRunStrip(regressionRuns)}${await renderRunOverview(selectedRegressionRun)}` : ""}
        ${resultsTab === "plots" ? `<div class="subtle" style="margin:14px 0 8px">Regression plots${selectedSim ? ` | ${selectedSim.name}` : ""}</div>${await renderPlotSlider(selectedRegressionRun, selectedSim ? selectedSim.name : "")}` : ""}
      `;
      $("resultsRunsTab").addEventListener("click", async () => {
        resultsTab = "runs";
        saveUiStateSoon();
        await renderResults();
      });
      $("resultsPlotsTab").addEventListener("click", async () => {
        resultsTab = "plots";
        saveUiStateSoon();
        await renderResults();
      });
      const prev = $("regPrev");
      const next = $("regNext");
      if (prev) prev.addEventListener("click", async () => {
        regressionWheelIndex -= 1;
        regressionTestIndex = 0;
        plotIndex = 0;
        saveUiStateSoon();
        await renderResults();
      });
      if (next) next.addEventListener("click", async () => {
        regressionWheelIndex += 1;
        regressionTestIndex = 0;
        plotIndex = 0;
        saveUiStateSoon();
        await renderResults();
      });
      document.querySelectorAll("[data-run-index]").forEach(button => {
        button.addEventListener("click", async () => {
          regressionWheelIndex = Number(button.dataset.runIndex);
          regressionTestIndex = 0;
          plotIndex = 0;
          saveUiStateSoon();
          await renderResults();
        });
      });
      document.querySelectorAll("[data-test-index]").forEach(button => {
        button.addEventListener("click", async () => {
          regressionTestIndex = Number(button.dataset.testIndex);
          plotIndex = 0;
          saveUiStateSoon();
          await renderResults();
        });
      });
      const plotPrev = $("plotPrev");
      const plotNext = $("plotNext");
      if (plotPrev) plotPrev.addEventListener("click", async () => {
        plotIndex -= 1;
        saveUiStateSoon();
        await renderResults();
      });
      if (plotNext) plotNext.addEventListener("click", async () => {
        plotIndex += 1;
        saveUiStateSoon();
        await renderResults();
      });
    }

    async function refreshAll() {
      restoringState = true;
      state.meta = await api("/api/meta");
      restoreState = await api("/api/state");
      $("root").textContent = state.meta.root;
      optionList($("opalxSource"), state.meta.opalx_choices, state.meta.default_opalx_choice);
      $("opalxBranch").value = state.meta.default_source_branch || state.meta.defaults.branch;
      optionList($("regBranch"), state.meta.regtests_branches, state.meta.defaults.regtests_branch);
      optionList($("config"), state.meta.configs, "debug-cpu.conf");
      $("refSourceRoot").value = state.meta.default_reference_source;
      optionList($("refDir"), [], "");
      $("publishDir").value = displayPath(state.meta.default_publish_dir);
      applySavedSelections();
      await refreshReferenceRtFiles(restoreState && restoreState.refDir ? restoreState.refDir : "");
      await refreshSourceBranch();
      updateReferenceExeLabel();
      await renderResults();
      await refreshTests();
      await refreshCommand();
      restoreState = null;
      restoringState = false;
    }

    async function startRun() {
      $("runBtn").disabled = true;
      $("status").textContent = "running";
      $("console").textContent = "";
      const run = await api("/api/run", { method: "POST", body: JSON.stringify(payload()) });
      const events = new EventSource(`/api/run/${run.id}/stream`);
      events.onmessage = (event) => {
        $("console").textContent += event.data.replaceAll("\\n", "\n");
        $("console").scrollTop = $("console").scrollHeight;
      };
      events.addEventListener("done", async () => {
        events.close();
        $("runBtn").disabled = false;
        $("status").textContent = "finished";
        state.meta = await api("/api/meta");
        await renderResults();
      });
    }

    ["opalxBranch", "regBranch", "config", "publishDir", "noGpl", "force", "compile", "unitTests", "regTests", "webOnly"].forEach(id => {
      document.addEventListener("change", (event) => {
        if (event.target && event.target.id === id) {
          refreshCommand();
          saveUiStateSoon();
        }
      });
    });
    $("opalxSource").addEventListener("change", async () => {
      await refreshSourceBranch();
      saveUiStateSoon();
    });
    $("runModeBtn").addEventListener("click", () => setMode("run"));
    $("refModeBtn").addEventListener("click", () => setMode("reference"));
    $("refSourceRoot").addEventListener("change", async () => {
      saveUiStateSoon();
      await refreshReferenceRtFiles();
    });
    $("refSearchRt").addEventListener("click", async () => {
      saveUiStateSoon();
      await refreshReferenceRtFiles($("refDir").value);
    });
    $("refDir").addEventListener("change", async () => {
      saveUiStateSoon();
      await scanReference();
    });
    $("refreshBtn").addEventListener("click", refreshAll);
    $("runBtn").addEventListener("click", startRun);
    $("clearTests").addEventListener("click", () => {
      state.selectedTests.clear();
      document.querySelectorAll("[data-test]").forEach(box => box.checked = false);
      refreshCommand();
      saveUiStateSoon();
    });
    $("refScan").addEventListener("click", scanReference);
    $("refRun").addEventListener("click", runReference);
    $("refWrite").addEventListener("click", writeReferenceRt);
    $("refCopyRepo").addEventListener("click", copyReferenceToRepo);

    refreshAll().catch(err => {
      $("console").textContent = err.stack || String(err);
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            text_response(self, APP_HTML)
        elif parsed.path == "/api/meta":
            opalx_sources = discover_opalx_sources()
            opalx_build_dirs = discover_opalx_build_dirs()
            opalx_choices = [
                {
                    "kind": "source",
                    "value": path,
                    "label": display_path(Path(path)),
                    "branch": current_branch(Path(path)),
                    "build_dir": matching_build_dir(Path(path), opalx_build_dirs),
                    "exe_dir": f"{matching_build_dir(Path(path), opalx_build_dirs)}/src" if matching_build_dir(Path(path), opalx_build_dirs) else "",
                }
                for path in opalx_sources
            ] + [
                {
                    "kind": "build",
                    "value": path,
                    "label": f"{display_path(Path(path))} (build)",
                    "branch": build_branch(Path(path)),
                    "source": str(build_source_dir(Path(path)) or ""),
                    "exe_dir": f"{path}/src",
                }
                for path in opalx_build_dirs
            ]
            default_opalx_source = opalx_sources[0] if opalx_sources else ""
            default_opalx_choice = default_opalx_source or (opalx_build_dirs[0] if opalx_build_dirs else "")
            source_repo = Path(default_opalx_source) if default_opalx_source else OPALX_CHECKOUT
            local_branches = list_workspace_branches()
            remote_branches: list[str] = []
            if source_repo.exists():
                remote_branches = list_remote_branches(source_repo)
            default_source_branch = current_branch(source_repo) if default_opalx_source else ""
            branches = [default_source_branch] if default_source_branch else (local_branches or ["master"])
            regtests_branches = list_regtests_branches() or ["master"]
            configs = list_configs()
            defaults = parse_config(configs[0]) if configs else {}
            if defaults.get("branch") not in branches:
                defaults["branch"] = branches[0]
            if defaults.get("regtests_branch") not in regtests_branches:
                defaults["regtests_branch"] = regtests_branches[0]
            json_response(
                self,
                {
                    "root": str(ROOT),
                    "home": str(Path.home()),
                    "workspace": str(WORKSPACE),
                    "opalx_checkout": str(OPALX_CHECKOUT),
                    "opalx_sources": opalx_sources,
                    "opalx_build_dirs": opalx_build_dirs,
                    "opalx_choices": opalx_choices,
                    "default_opalx_source": default_opalx_source,
                    "default_opalx_choice": default_opalx_choice,
                    "default_source_branch": default_source_branch,
                    "regtests_checkout": str(REGTESTS_CHECKOUT),
                    "default_reference_source": display_path(DEFAULT_REFERENCE_SOURCE),
                    "reference_rt_files": list_reference_rt_files(),
                    "build_root": str(BUILD_ROOT),
                    "default_publish_dir": display_path(DEFAULT_PUBLISH_DIR),
                    "branches": branches,
                    "local_branches": local_branches,
                    "regtests_branches": regtests_branches,
                    "remote_branches": remote_branches,
                    "configs": configs,
                    "defaults": defaults,
                    "history": load_history()[:20],
                },
            )
        elif parsed.path == "/api/tests":
            json_response(self, list_tests(""))
        elif parsed.path == "/api/source-branch":
            qs = urllib.parse.parse_qs(parsed.query)
            raw_path = (qs.get("path") or [""])[0]
            path = Path(raw_path).expanduser() if raw_path else Path("/__missing__")
            json_response(
                self,
                {
                    "path": str(path),
                    "branch": current_branch(path),
                    "branches": list_local_branches(path),
                    "is_git_repo": is_git_repo(path),
                },
            )
        elif parsed.path == "/api/results":
            json_response(self, list_results())
        elif parsed.path == "/api/plots":
            qs = urllib.parse.parse_qs(parsed.query)
            run_id = (qs.get("run_id") or [""])[0]
            json_response(self, list_run_plots(run_id))
        elif parsed.path == "/api/run-summary":
            qs = urllib.parse.parse_qs(parsed.query)
            run_id = (qs.get("run_id") or [""])[0]
            json_response(self, run_summary(run_id))
        elif parsed.path == "/api/state":
            json_response(self, load_ui_state())
        elif parsed.path == "/api/reference/scan":
            qs = urllib.parse.parse_qs(parsed.query)
            path = (qs.get("path") or [""])[0]
            info = reference_info(path)
            if info["simname"]:
                info["selected"] = existing_rt_columns(Path(info["path"]), info["simname"])
            json_response(self, info)
        elif parsed.path == "/api/reference/rt-files":
            qs = urllib.parse.parse_qs(parsed.query)
            root_text = (qs.get("root") or [""])[0] or "$HOME"
            root = expand_path_text(root_text)
            json_response(
                self,
                {
                    "root": str(root),
                    "root_display": display_path(root),
                    "files": list_reference_rt_files(root_text),
                },
            )
        elif parsed.path.startswith("/api/run/") and parsed.path.endswith("/stream"):
            run_id = parsed.path.split("/")[3]
            self.stream_run(run_id)
        elif parsed.path == "/file":
            qs = urllib.parse.parse_qs(parsed.query)
            path = Path((qs.get("path") or [""])[0]).resolve()
            self.serve_file(path)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/command":
            command, _ = build_command(payload)
            json_response(self, {"command": command})
        elif self.path == "/api/run":
            record = start_run(payload)
            json_response(self, asdict(record))
        elif self.path == "/api/state":
            save_ui_state(payload)
            json_response(self, {"ok": True})
        elif self.path == "/api/reference/run":
            json_response(
                self,
                run_make_reference(payload.get("path", ""), payload.get("opalx_exe_path", ""), int(payload.get("ranks", 1))),
            )
        elif self.path == "/api/reference/write-rt":
            json_response(self, write_reference_rt(payload))
        elif self.path == "/api/reference/copy-to-repo":
            json_response(self, copy_reference_to_repo(payload.get("path", "")))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def stream_run(self, run_id: str) -> None:
        log_queue = RUN_LOGS.get(run_id)
        if log_queue is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        while True:
            item = log_queue.get()
            if item is None:
                self.wfile.write(b"event: done\ndata: done\n\n")
                self.wfile.flush()
                break
            data = item.replace("\n", "\\n")
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

    def serve_file(self, path: Path) -> None:
        allowed_roots = [DEFAULT_PUBLISH_DIR.resolve(), ROOT.resolve()]
        if not any(str(path).startswith(str(root)) for root in allowed_roots):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[opalx-gui] {self.address_string()} - {format % args}")


def main() -> None:
    host = os.environ.get("OPALX_GUI_HOST", "127.0.0.1")
    port = int(os.environ.get("OPALX_GUI_PORT", "8765"))
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"Port {port} is already in use.")
            print(f"Open http://{host}:{port} if OPALX Lab is already running, or start another instance with:")
            print(f"  OPALX_GUI_PORT={port + 1} python3 -B gui/opalx_gui.py")
            return
        raise
    print(f"OPALX Lab listening on http://{host}:{port}")
    print(f"NightlyBuildX root: {ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOPALX Lab stopped.")


if __name__ == "__main__":
    main()
