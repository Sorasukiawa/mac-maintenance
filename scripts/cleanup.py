#!/usr/bin/env python3
"""Preview exact targets, recheck evidence and record observed results. Never delete."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from maintenance_common import (DEFAULT_PREFERENCES, absolute_path, app_info, command,
    digest, emit, intersects, now, preferences, read_json, same_entry, snapshot, volume)


def owner_check(names):
    if not names:
        return {"status": "not_checked", "reason": "Owner processes were not supplied"}
    if not isinstance(names, list) or any(not isinstance(n, str) or not n or "/" in n for n in names):
        raise ValueError("owner_processes must be a list of exact executable basenames")
    result = command(["/bin/ps", "-axo", "comm="], 10)
    if result["status"] != "ok" or result.get("stderr"):
        return {"status": "unknown", "evidence": result}
    running = {Path(line.strip()).name for line in result["stdout"].splitlines()}
    active = sorted(set(names) & running)
    return {"status": "active" if active else "not_observed", "names": names,
            "active": active, "checked_at": now(), "handles_checked": False}


def replacement_check(item, prefs):
    result = {"status": "not_applicable"}
    if item.get("kind") != "obsolete_app":
        return result
    replacement = item.get("replacement", {})
    result = {"status": "blocked", "reason": "Replacement availability and dependencies are not verified"}
    if not prefs["remove_old_versions_if_replacement_verified"]:
        result["reason"] = "Old-version removal disabled in selected preferences"
        return result
    if not isinstance(replacement, dict) or replacement.get("running_verified") is not True or \
       replacement.get("dependencies_checked") is not True or not replacement.get("evidence"):
        return result
    try:
        old_path, new_path = absolute_path(item["path"]), absolute_path(replacement["path"])
        if intersects(old_path, new_path):
            raise ValueError("Replacement overlaps removal target")
        old, new = app_info(old_path), app_info(new_path)
        def version(value):
            if not re.fullmatch(r"\d+(?:\.\d+)*", value):
                raise ValueError("Non-numeric product versions need a product-specific manual comparison")
            return tuple(map(int, value.split(".")))
        left, right = version(old["version"]), version(new["version"])
        width = max(len(left), len(right))
        if old["bundle_id"] != new["bundle_id"] or right + (0,) * (width - len(right)) <= left + (0,) * (width - len(left)):
            raise ValueError("Replacement is not a newer version of the same bundle ID")
        evidence = snapshot(str(new_path))
        if evidence["status"] != "ok":
            raise ValueError("Replacement snapshot incomplete")
        return {"status": "reported_verified", "old": old, "new": new, "snapshot": evidence,
                "evidence": replacement["evidence"],
                "note": "Running and dependency evidence is supplied by the operator; filesystem metadata cannot prove compatibility"}
    except (OSError, ValueError, KeyError) as error:
        result["reason"] = str(error)
        return result


def load_targets(path):
    value = read_json(path)
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("targets"), list) or not value["targets"]:
        raise ValueError("Expected version 1 and a nonempty targets array")
    seen = set()
    for item in value["targets"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in seen:
            raise ValueError("Each target needs a unique nonempty string id")
        seen.add(item["id"])
        for key in ("path", "kind", "reason"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError("Missing target field: " + key)
        absolute_path(item["path"])
        if item["kind"] not in ("cache", "obsolete_app", "installer", "user_selected"):
            raise ValueError("Unsupported target kind")
    return value["targets"]


def preview(args):
    prefs = preferences(args.preferences)
    items = load_targets(args.targets)
    protected = [Path(p).expanduser().resolve() for p in prefs["protect_paths"]]
    broad = {Path("/"), Path("/Applications"), Path.home(), Path.home() / "Library",
             Path("/System"), Path("/Library"), Path("/Users"), Path("/Volumes"),
             Path("/System/Volumes/Data"), Path.home() / "Library/Caches"}
    targets = []
    paths = [absolute_path(item["path"]) for item in items]
    for index, (item, path) in enumerate(zip(items, paths)):
        reasons = []
        overlaps = any(index != other and intersects(path, candidate) for other, candidate in enumerate(paths))
        if overlaps:
            reasons.append("overlapping_targets")
        if any(same_entry(path, root) for root in broad):
            reasons.append("broad_root_requires_precise_children")
        if any(intersects(path.resolve(), candidate) for candidate in protected):
            reasons.append("protected_path_intersection")
        # Do not traverse known-overbroad/protected trees merely to reject them.
        snap = {"status": "blocked", "allocated_bytes": None} if reasons else snapshot(str(path))
        if snap["status"] != "ok":
            reasons.append("snapshot_" + snap["status"])
        owners = owner_check(item.get("owner_processes"))
        if owners["status"] in ("active", "unknown"):
            reasons.append("owner_" + owners["status"])
        replacement = replacement_check(item, prefs)
        if replacement["status"] == "blocked":
            reasons.append("replacement_unverified")
        targets.append({"id": item["id"], "path": str(path), "request": item,
                        "status": "blocked" if reasons else "review", "reasons": reasons,
                        "snapshot": snap, "owner_check": owners, "replacement_check": replacement,
                        "volume_before": volume(path)})
    result = {"version": 1, "plan_id": str(uuid.uuid4()), "created_at": now(),
              "preferences_digest": digest(prefs), "targets": targets,
              "total_target_allocated_bytes": sum(t["snapshot"]["allocated_bytes"] for t in targets)
                   if all(t["status"] != "blocked" and not t["snapshot"].get("hardlinked_file_count")
                          for t in targets) else None,
              "note": "Review evidence only. No deletion, approval or reclaimable-space guarantee."}
    result["plan_digest"] = digest(result)
    emit(result, args.output)
    return 0


def load_plan(path):
    plan = read_json(path)
    if not isinstance(plan, dict) or plan.get("version") != 1 or not isinstance(plan.get("targets"), list):
        raise ValueError("Invalid plan")
    expected = plan.get("plan_digest")
    if not expected or expected != digest({k: v for k, v in plan.items() if k != "plan_digest"}):
        raise ValueError("Plan changed or lacks an integrity digest; generate a fresh preview")
    return plan


def verify(args):
    plan = load_plan(args.plan)
    prefs = preferences(args.preferences)
    prefs_same = digest(prefs) == plan["preferences_digest"]
    checks = []
    for target in plan["targets"]:
        current = snapshot(target["path"])
        owners = owner_check(target["request"].get("owner_processes"))
        replacement = replacement_check(target["request"], prefs)
        previous_replacement = target["replacement_check"]
        replacement_same = replacement.get("status") == previous_replacement.get("status") and \
            replacement.get("snapshot", {}).get("fingerprint") == previous_replacement.get("snapshot", {}).get("fingerprint")
        unchanged = target["status"] != "blocked" and current["status"] == "ok" and \
            current["fingerprint"] == target["snapshot"].get("fingerprint") and \
            owners["status"] not in ("active", "unknown") and replacement_same
        checks.append({"id": target["id"], "unchanged": unchanged, "snapshot": current,
                       "owner_check": owners, "replacement_unchanged": replacement_same})
    unchanged = prefs_same and all(item["unchanged"] for item in checks)
    emit({"version": 1, "plan_id": plan["plan_id"], "checked_at": now(), "unchanged": unchanged,
          "preferences_unchanged": prefs_same, "targets": checks,
          "note": "Unchanged metadata is not authorization, a writer lock, a handle check or proof of rebuildability."}, args.output)
    return 0 if unchanged else 2


def append_log(path, events):
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Log must be a regular file")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.fstat(handle.fileno()).st_size > 16 * 1024 * 1024:
            raise ValueError("Log exceeds 16 MiB; select a new task log")
        handle.seek(0)
        for line in handle:
            if not line.endswith("\n"):
                raise ValueError("Existing log has an incomplete line; select a new log and inspect the previous write")
            try:
                old = json.loads(line)
                if not isinstance(old, dict) or old.get("version") != 1 or not all(
                    isinstance(old.get(key), str) and old[key]
                    for key in ("event_id", "plan_id", "id", "observed_status")):
                    raise ValueError("Invalid event")
            except (ValueError, TypeError):
                raise ValueError("Existing file is not a maintenance event log; select a new path") from None
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record(args):
    plan = load_plan(args.plan)
    results = read_json(args.results)
    if not isinstance(results, dict) or results.get("version") != 1 or not isinstance(results.get("results"), list):
        raise ValueError("Expected version 1 and results array")
    indexed = {target["id"]: target for target in plan["targets"]}
    events, seen = [], set()
    for supplied in results["results"]:
        if not isinstance(supplied, dict) or supplied.get("id") not in indexed or supplied["id"] in seen:
            raise ValueError("Unknown or duplicate result target")
        seen.add(supplied["id"])
        target = indexed[supplied["id"]]
        if supplied.get("action") not in ("removed", "moved", "manual", "skipped"):
            raise ValueError("Unsupported recorded action")
        current, before = snapshot(target["path"]), target["snapshot"]
        status, removed = "reported_only", None
        destination = None
        if current["status"] == "missing" and supplied["action"] == "removed":
            status, removed = "observed_absent", before.get("allocated_bytes")
        elif current["status"] == "ok" and supplied["action"] in ("removed", "moved"):
            status, removed = "still_present", 0
        elif current["status"] == "missing" and supplied["action"] == "moved":
            destination = snapshot(str(absolute_path(supplied.get("destination", ""))))
            if destination["status"] == "ok" and (destination["device"], destination["inode"]) == (before.get("device"), before.get("inode")):
                status, removed = "moved_same_volume", 0
            else:
                status = "move_not_verified"
        elif current["status"] in ("unknown", "blocked"):
            status = "observation_incomplete"
        after = volume(target["path"])
        volume_before = target["volume_before"]
        delta = after["available_bytes"] - volume_before["available_bytes"] if \
            after["status"] == volume_before["status"] == "ok" and after["device"] == volume_before["device"] else None
        events.append({"version": 1, "event_id": str(uuid.uuid4()), "plan_id": plan["plan_id"],
                       "recorded_at": now(), "id": supplied["id"], "path": target["path"],
                       "reported": supplied, "observed_status": status, "snapshot_after": current,
                       "destination_snapshot": destination, "target_bytes_removed": removed,
                       "source_path_bytes_decrease": before.get("allocated_bytes") if current["status"] == "missing"
                           else max(0, before["allocated_bytes"] - current["allocated_bytes"])
                           if current["status"] == before["status"] == "ok" else None,
                       "volume_available_delta_bytes": delta, "reclaimed_bytes": None,
                       "note": "Target disappearance and volume free-space delta are separate observations; neither proves attributable APFS reclamation."})
    append_log(args.log, events)
    emit({"version": 1, "events": events, "log": args.log})
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    pre = subs.add_parser("preview")
    pre.add_argument("--targets", required=True)
    pre.add_argument("--preferences", default=str(DEFAULT_PREFERENCES))
    pre.add_argument("--output")
    ver = subs.add_parser("verify")
    ver.add_argument("--plan", required=True)
    ver.add_argument("--preferences", default=str(DEFAULT_PREFERENCES))
    ver.add_argument("--output")
    rec = subs.add_parser("record")
    rec.add_argument("--plan", required=True)
    rec.add_argument("--results", required=True)
    rec.add_argument("--log", required=True)
    args = parser.parse_args()
    try:
        return {"preview": preview, "verify": verify, "record": record}[args.operation](args)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        emit({"status": "error", "error": str(error)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
