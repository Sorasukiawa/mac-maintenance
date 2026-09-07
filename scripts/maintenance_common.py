"""Read-only evidence helpers. Python 3.10+, standard library only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import tempfile
import time
from xml.parsers.expat import ExpatError

DEFAULT_PREFERENCES = Path(__file__).resolve().parents[1] / "config/preferences.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def preferences(path=DEFAULT_PREFERENCES):
    value = read_json(path)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported preferences version")
    allowed = {"version", "skip_update_bundle_ids", "manager_only_bundle_prefixes",
               "protect_paths", "remove_old_versions_if_replacement_verified"}
    if set(value) - allowed:
        raise ValueError("Unknown preference keys: " + ", ".join(sorted(set(value) - allowed)))
    for key in ("skip_update_bundle_ids", "protect_paths"):
        if not isinstance(value.get(key), list) or any(not isinstance(x, str) or not x for x in value[key]):
            raise ValueError("Invalid preference: " + key)
    managers = value.get("manager_only_bundle_prefixes")
    if not isinstance(managers, dict) or any(not isinstance(k, str) or not k or
        not isinstance(v, str) or not v for k, v in managers.items()):
        raise ValueError("Invalid manager_only_bundle_prefixes")
    if not isinstance(value.get("remove_old_versions_if_replacement_verified"), bool):
        raise ValueError("Invalid old-version preference")
    for item in value["protect_paths"]:
        if not Path(item).expanduser().is_absolute():
            raise ValueError("Protected paths must be absolute")
    return value


def update_policy(bundle_id, prefs):
    if bundle_id in prefs["skip_update_bundle_ids"]:
        return {"mode": "skip", "source": "preferences"}
    for prefix in sorted(prefs["manager_only_bundle_prefixes"], key=len, reverse=True):
        if bundle_id.startswith(prefix):
            return {"mode": "manager_only", "manager": prefs["manager_only_bundle_prefixes"][prefix],
                    "source": "preferences"}
    return {"mode": "official_source", "source": "default"}


def write_new(path, content):
    """No clobber, including dangling symlinks. The caller creates the parent."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def emit(value, output=None):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        write_new(output, text)
    print(text, end="")


def command(argv, timeout=15, limit=512 * 1024):
    """Bound time/output; no shell or automatic package-manager refresh."""
    started = time.monotonic()
    result = {"argv": argv, "checked_at": now()}
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1"}
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            with subprocess.Popen(argv, stdout=out, stderr=err, env=env, start_new_session=True) as process:
                try:
                    process.wait(timeout=timeout)
                    result["status"] = "ok" if process.returncode == 0 else "unknown"
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    result["status"] = "timeout"
                result["returncode"] = process.returncode
            for key, handle in (("stdout", out), ("stderr", err)):
                handle.seek(0)
                raw = handle.read(limit + 1)
                result[key] = raw[:limit].decode("utf-8", errors="replace")
                if len(raw) > limit:
                    result["truncated"] = True
                    if result["status"] == "ok":
                        result["status"] = "unknown"
    except OSError as error:
        result.update(status="unavailable", error=str(error))
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def redact_hardware(value):
    """Remove hardware identity fields, including new vendor-specific key variants."""
    if isinstance(value, dict):
        return {key: redact_hardware(item) for key, item in value.items()
                if not any(token in key.lower() for token in
                           ("serial", "uuid", "udid", "address", "machine_name", "computer_name"))}
    if isinstance(value, list):
        return [redact_hardware(item) for item in value]
    return value


def read_plist(path):
    try:
        with open(path, "rb") as handle:
            return plistlib.load(handle)
    except (plistlib.InvalidFileException, ValueError, ExpatError):
        result = command(["/usr/bin/plutil", "-convert", "json", "-o", "-", str(path)])
        if result["status"] != "ok":
            raise ValueError("plist unavailable or unsupported: " + str(path))
        return json.loads(result["stdout"])


def app_info(path):
    path = Path(path)
    candidates = [path / "Contents/Info.plist", path / "Info.plist"]
    wrapper = path / "Wrapper"
    if wrapper.is_dir() and not wrapper.is_symlink():
        candidates += sorted(wrapper.glob("*.app/Contents/Info.plist"))
        candidates += sorted(wrapper.glob("*.app/Info.plist"))
    info_path = next((p for p in candidates if p.is_file() and p.resolve() == p), None)
    if info_path is None:
        raise ValueError("No readable, unlinked Info.plist: " + str(path))
    value = read_plist(info_path)
    if not isinstance(value, dict) or not isinstance(value.get("CFBundleIdentifier"), str):
        raise ValueError("Missing bundle ID: " + str(path))
    return {"path": str(path), "bundle_id": value["CFBundleIdentifier"],
            "name": str(value.get("CFBundleDisplayName", value.get("CFBundleName", path.stem))),
            "version": str(value.get("CFBundleShortVersionString", "")),
            "build": str(value.get("CFBundleVersion", "")),
            "minimum_system": str(value.get("LSMinimumSystemVersion", "")),
            "wrapped": info_path.is_relative_to(wrapper),
            "source_hint": "app_store_receipt" if (path / "Contents/_MASReceipt/receipt").is_file()
                           else "sparkle_feed_present" if value.get("SUFeedURL") else "unconfirmed"}


def inventory(roots, prefs, max_depth=3, max_entries=10000):
    apps, gaps = [], []
    seen = set()
    count = 0

    def visit(path, depth):
        nonlocal count
        if count >= max_entries:
            raise ValueError("Application inventory entry limit reached")
        count += 1
        if path.is_symlink() or path.resolve() != path:
            gaps.append({"path": str(path), "reason": "symbolic_link_skipped"})
            return
        if not path.exists():
            gaps.append({"path": str(path), "reason": "missing"})
            return
        if path.suffix.lower() == ".app":
            if str(path) not in seen:
                seen.add(str(path))
                try:
                    app = app_info(path)
                    app["update_policy"] = update_policy(app["bundle_id"], prefs)
                    apps.append(app)
                except (OSError, ValueError) as error:
                    gaps.append({"path": str(path), "reason": str(error)})
            return
        if path.is_dir():
            if depth >= max_depth:
                gaps.append({"path": str(path), "reason": "depth_limit"})
                return
            try:
                for child in sorted(path.iterdir()):
                    visit(child, depth + 1)
            except OSError as error:
                gaps.append({"path": str(path), "reason": str(error)})
    try:
        for root in roots:
            path = Path(os.path.abspath(Path(root).expanduser()))
            visit(path, 0)
    except ValueError as error:
        gaps.append({"reason": str(error)})
    return apps, gaps


def absolute_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Use an absolute path without '..'")
    return path


def identity(path):
    try:
        info = path.stat()
        return info.st_dev, info.st_ino
    except FileNotFoundError:
        return None


def same_entry(a, b):
    found = identity(a)
    return a == b or (found is not None and found == identity(b))


def intersects(a, b):
    if a == b or a.is_relative_to(b) or b.is_relative_to(a):
        return True
    # APFS can be case insensitive. String resolve() does not normalize case.
    a_id, b_id = identity(a), identity(b)
    return (a_id is not None and any(a_id == identity(p) for p in (b, *b.parents))) or \
           (b_id is not None and any(b_id == identity(p) for p in (a, *a.parents)))


def open_parent_no_links(path):
    """Anchor every ancestor at '/', never redirect through a swapped symlink."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def volume(path):
    probe = Path(path)
    try:
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        info = os.statvfs(probe)
        return {"status": "ok", "device": probe.stat().st_dev,
                "available_bytes": info.f_bavail * info.f_frsize, "checked_at": now()}
    except OSError as error:
        return {"status": "unknown", "available_bytes": None, "error": str(error)}


def snapshot(value, max_entries=50000, timeout=10):
    """Metadata fingerprint, no file contents, no link/mount traversal.

    This is observational evidence, not a lock or a deletion transaction.
    Directory FDs prevent a swapped child link from redirecting traversal.
    """
    result = {"status": "unknown", "allocated_bytes": None, "logical_bytes": None,
              "entry_count": None, "fingerprint": None, "checked_at": now()}
    rows, files = [], set()
    allocated = logical = links = hardlinks = 0
    started = time.monotonic()

    def metadata(info):
        return [info.st_mode, info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns, info.st_nlink, info.st_blocks]

    def walk(parent_fd, name, relative, depth=0):
        nonlocal allocated, logical, links, hardlinks
        if len(rows) >= max_entries or depth > 256 or time.monotonic() - started > timeout:
            raise ValueError("snapshot_limit_or_timeout")
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if info.st_dev != root_info.st_dev:
            raise ValueError("nested_mount_skipped")
        row = [relative, *metadata(info)]
        if stat.S_ISLNK(info.st_mode):
            row.append(os.readlink(name, dir_fd=parent_fd))
            links += 1
        elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("special_file_requires_manual_inspection")
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            hardlinks += 1
        rows.append(row)
        identity = (info.st_dev, info.st_ino)
        if identity not in files:
            files.add(identity)
            allocated += info.st_blocks * 512
            logical += info.st_size
        if stat.S_ISDIR(info.st_mode):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                if metadata(os.fstat(fd)) != metadata(info):
                    raise ValueError("changed_during_scan")
                names = []
                with os.scandir(fd) as entries:
                    for entry in entries:
                        names.append(entry.name)
                        if len(names) + len(rows) > max_entries or time.monotonic() - started > timeout:
                            raise ValueError("snapshot_limit_or_timeout")
                for child in sorted(names):
                    walk(fd, child, relative + "/" + child, depth + 1)
                if metadata(os.fstat(fd)) != metadata(info):
                    raise ValueError("changed_during_scan")
            finally:
                os.close(fd)
        if metadata(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != metadata(info):
            raise ValueError("changed_during_scan")

    try:
        path = absolute_path(value)
        result["path"] = str(path)
        if path.is_symlink() or path.resolve() != path:
            result.update(status="blocked", reason="symbolic_link_or_alias_path")
            return result
        parent_fd = open_parent_no_links(path)
        name = path.name or "."
        try:
            root_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(root_info.st_mode):
                raise ValueError("root_became_symlink")
            walk(parent_fd, name, ".")
            check_fd = open_parent_no_links(path)
            try:
                if metadata(os.stat(name, dir_fd=check_fd, follow_symlinks=False)) != metadata(root_info):
                    raise ValueError("root_changed_during_scan")
            finally:
                os.close(check_fd)
        finally:
            os.close(parent_fd)
        result.update(status="ok", allocated_bytes=allocated, logical_bytes=logical,
                      entry_count=len(rows), symlink_count=links, hardlinked_file_count=hardlinks,
                      fingerprint=digest(rows),
                      device=root_info.st_dev, inode=root_info.st_ino)
    except FileNotFoundError as error:
        # Missing descendants mean an incomplete scan, not an absent target.
        result.update(status="unknown" if rows else "missing", reason=str(error))
    except (OSError, ValueError, RuntimeError) as error:
        result.update(status="unknown", reason=str(error))
    return result
