#!/usr/bin/env python3
"""Repeatable Mac inventory. No updates, deletion, service starts or UI actions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import shutil
import sys

from maintenance_common import (DEFAULT_PREFERENCES, LOCAL_PREFERENCES, command, emit,
                                inventory, now, preferences, redact_hardware,
                                redact_text, write_new)


def system_checks(quick, online):
    jobs = [
        ("system", ["/usr/bin/sw_vers"], 10),
        ("architecture", ["/usr/bin/uname", "-m"], 10),
        ("disk_free", ["/bin/df", "-k", "/System/Volumes/Data"], 10),
        ("memory_pressure", ["/usr/bin/memory_pressure", "-Q"], 10),
        ("vm", ["/usr/bin/vm_stat"], 10),
        ("swap", ["/usr/sbin/sysctl", "vm.swapusage"], 10),
        ("thermal", ["/usr/bin/pmset", "-g", "therm"], 10),
        ("hardware", ["/usr/sbin/system_profiler", "SPHardwareDataType", "SPPowerDataType",
                      "SPNVMeDataType", "-detailLevel", "mini", "-json"], 25),
    ]
    if not quick:
        jobs += [
            ("system_extensions", ["/usr/bin/systemextensionsctl", "list"], 15),
            ("backup_status", ["/usr/bin/tmutil", "status"], 10),
            ("backup_latest", ["/usr/bin/tmutil", "latestbackup"], 15),
            ("developer_directory", ["/usr/bin/xcode-select", "-p"], 10),
            ("peripheral_types", ["/usr/sbin/system_profiler", "-listDataTypes"], 15),
        ]
    brew = shutil.which("brew")
    if brew:
        jobs.append(("brew_outdated_local_metadata", [brew, "outdated", "--json=v2"], 30))
        if not quick:
            jobs.append(("brew_services", [brew, "services", "list"], 20))
    if online:
        jobs.append(("system_updates", ["/usr/sbin/softwareupdate", "--list"], 45))

    def run(job):
        name, argv, timeout = job
        result = command(argv, timeout)
        if name == "hardware":
            raw = result.pop("stdout", "")
            result.pop("stderr", None)  # Do not retain unstructured identity fields.
            if result["status"] == "ok":
                try:
                    result["data"] = redact_hardware(json.loads(raw))
                except ValueError:
                    result.update(status="unknown", error="invalid_profiler_json")
        elif name in ("backup_status", "backup_latest"):
            if "stdout" in result:
                result["stdout"] = redact_text(result["stdout"])
            if "stderr" in result:
                result["stderr"] = redact_text(result["stderr"])
        return name, result

    with ThreadPoolExecutor(max_workers=4) as pool:
        checks = dict(pool.map(run, jobs))
    if not quick:
        types = checks.get("peripheral_types", {}).get("stdout", "")
        selected = [item for item in ("SPThunderboltDataType", "SPDisplaysDataType") if item in types]
        usb_type = next((item for item in ("SPUSBHostDataType", "SPUSBDataType") if item in types), None)
        if usb_type:
            selected.append(usb_type)
        if selected:
            result = command(["/usr/sbin/system_profiler", *selected, "-detailLevel", "mini", "-json"], 30)
            raw = result.pop("stdout", "")
            result.pop("stderr", None)
            if result["status"] == "ok":
                try:
                    result["data"] = redact_hardware(json.loads(raw))
                except ValueError:
                    result.update(status="unknown", error="invalid_profiler_json")
            checks["peripherals"] = result
    return checks


def storage_checks(roots):
    def run(path):
        path = Path(os.path.abspath(Path(path).expanduser()))
        if path.is_symlink() or path.resolve() != path:
            return {"path": str(path), "status": "unknown", "allocated_bytes": None,
                    "partial_allocated_bytes": None, "reason": "symbolic_link_skipped"}
        result = command(["/usr/bin/du", "-xsk", "--", str(path)], 15)
        item = {"path": str(path), "status": result["status"], "allocated_bytes": None,
                "partial_allocated_bytes": None, "evidence": result,
                "candidate_status": "requires_purpose_and_activity_review"}
        parsed = None
        if result.get("stdout"):
            try:
                parsed = int(result["stdout"].split()[0]) * 1024
            except (ValueError, IndexError):
                parsed = None
        if result["status"] == "ok" and not result.get("stderr") and parsed is not None:
            item["allocated_bytes"] = parsed
        else:
            item["status"] = "unknown"
            if parsed is not None and path.exists():
                item["partial_allocated_bytes"] = parsed
        return item
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(run, roots))


def check_summary(name, item):
    if item.get("status") != "ok":
        return str(item.get("error") or item.get("reason") or item.get("stderr", "").strip().splitlines()[:1] or "-")
    stdout = item.get("stdout", "").strip()
    if name == "system":
        return " / ".join(line.strip() for line in stdout.splitlines() if line.strip())
    if name == "disk_free":
        rows = [line.split() for line in stdout.splitlines() if line.strip()]
        if len(rows) >= 2 and len(rows[-1]) >= 4:
            try:
                return f"可用 {int(rows[-1][3]) * 1024 / 1024**3:.2f} GiB"
            except ValueError:
                pass
    if name == "brew_outdated_local_metadata":
        try:
            data = json.loads(stdout)
            return f"formulae {len(data.get('formulae', []))} 个, casks {len(data.get('casks', []))} 个"
        except ValueError:
            pass
    if name in ("hardware", "peripherals"):
        return "已采集脱敏 JSON"
    first = next((line.strip() for line in stdout.splitlines() if line.strip()), "-")
    return first[:80] + ("..." if len(first) > 80 else "")


def report(result):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# Mac 维护检查", "", "检查时间：" + result["generated_at"], "",
             "本报告是只读盘点。更新匹配、专业软件可用性、驱动适用性与清理边界仍按 Skill 核实。", "",
             f"应用 {len(result['applications'])} 个；未覆盖或需补查 {len(result['coverage_gaps'])} 项。", "",
             "## 系统检查", "", "| 检查 | 状态 | 摘要 |", "|---|---|---|"]
    for name, item in result["checks"].items():
        lines.append(f"| {cell(name)} | {cell(item['status'])} | {cell(check_summary(name, item))} |")
    lines += ["", "## 应用", "", "| 应用 | 版本 / build | 更新规则 |", "|---|---|---|"]
    for item in result["applications"]:
        lines.append(f"| {cell(item['name'])} | {cell(item['version'])} / {cell(item['build'])} | {cell(item['update_policy']['mode'])} |")
    lines += ["", "## 目录占用", "", "这些数值不代表可清理容量，父子目录可能重叠。", ""]
    for item in result["storage"]:
        if item["allocated_bytes"] is not None:
            size = f"{item['allocated_bytes'] / 1024**3:.2f} GiB"
        elif item.get("partial_allocated_bytes") is not None:
            size = f"未确认，可读部分约 {item['partial_allocated_bytes'] / 1024**3:.2f} GiB"
        else:
            size = "未确认"
        lines.append(f"- {cell(item['path'])}：{size}（{item['status']}）")
    lines += ["", "## 未覆盖与补查", ""]
    for gap in result["coverage_gaps"]:
        lines.append("- " + cell(json.dumps(gap, ensure_ascii=False)))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preferences", default=None)
    parser.add_argument("--quick", action="store_true", help="Skip peripheral, backup and service detail")
    parser.add_argument("--online", action="store_true", help="Also ask softwareupdate for matching OS updates")
    parser.add_argument("--apps-only", action="store_true", help="Only read app metadata; no system audit commands (plutil may parse legacy plists)")
    parser.add_argument("--app-root", action="append")
    parser.add_argument("--storage-root", action="append")
    parser.add_argument("--output", help="Create a new private JSON file; never overwrite")
    parser.add_argument("--report", help="Create a new Chinese Markdown report")
    args = parser.parse_args()
    explicit_prefs = args.preferences is not None
    args.preferences = args.preferences or str(DEFAULT_PREFERENCES)
    try:
        if not args.apps_only and platform.system() != "Darwin":
            raise ValueError("Host audit requires macOS; use --apps-only for fixtures")
        prefs = preferences(args.preferences)
        apps, gaps = inventory(args.app_root or ["/Applications", "~/Applications"], prefs)
        checks = {} if args.apps_only else system_checks(args.quick, args.online)
        storage = [] if args.apps_only else storage_checks(args.storage_root or
            ["~/Library/Caches", "~/Library/Logs", "~/Downloads"])
        gaps.extend({"check": key, "status": value["status"]} for key, value in checks.items()
                    if value["status"] != "ok")
        gaps.extend({"path": item["path"], "reason": "storage_scan_incomplete",
                     **({"partial_allocated_bytes": item["partial_allocated_bytes"]}
                        if item.get("partial_allocated_bytes") is not None else {})}
                    for item in storage if item["status"] != "ok")
        if not explicit_prefs and LOCAL_PREFERENCES.exists():
            gaps.append({"reason": "Local preferences file config/preferences.local.json exists but was not passed via --preferences"})
        gaps += [{"reason": "App update availability, architecture, signing, project compatibility and vendor firmware matching require targeted checks"},
                 {"reason": "Background items, active remote connections, full backups, external volumes and user data are not exhaustively inventoried"}]
        if not args.online:
            gaps.append({"reason": "OS update availability not queried; use --online or the system updater"})
        if not args.apps_only and not shutil.which("brew"):
            gaps.append({"reason": "Homebrew not found on PATH"})
        if args.quick:
            gaps.append({"reason": "Quick mode omits peripheral, extension, backup and service detail"})
        result = {"version": 1, "generated_at": now(), "scope": vars(args),
                  "preferences": prefs, "checks": checks, "applications": apps,
                  "storage": storage, "coverage_gaps": gaps}
        # Preflight both destinations before writing either; O_EXCL remains authoritative.
        for path in (args.output, args.report):
            if path and (Path(path).exists() or Path(path).is_symlink()):
                raise FileExistsError("Output already exists: " + path)
        if args.output and args.report and Path(args.output).absolute() == Path(args.report).absolute():
            raise ValueError("JSON output and Markdown report must use different files")
        if args.report:
            write_new(args.report, report(result))
        emit(result, args.output)
        return 0
    except (OSError, ValueError) as error:
        emit({"status": "error", "error": str(error)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
