import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import maintenance_common as common


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="maintenance-test-")
        self.base = Path(self.temp.name).resolve()
        self.prefs = self.base / "preferences.json"
        self.config = {
            "version": 1,
            "skip_update_bundle_ids": ["example.resolve"],
            "manager_only_bundle_prefixes": {"example.adobe.": "Creative Cloud"},
            "protect_paths": [],
            "remove_old_versions_if_replacement_verified": True,
        }
        self.prefs.write_text(json.dumps(self.config))
        self.cache = self.base / "cache"
        self.cache.mkdir()
        (self.cache / "entry.bin").write_bytes(b"original")

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, script, *args, expected=0):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
            text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(r.returncode, expected, r.stderr + r.stdout)
        self.assertTrue(r.stdout.strip(), "CLI must return JSON: " + r.stderr)
        return json.loads(r.stdout)

    def preview(self, **overrides):
        item = {"id": "cache", "path": str(self.cache), "kind": "cache",
                "reason": "Disposable fixture cache", **overrides}
        src = self.base / "targets.json"
        src.write_text(json.dumps({"version": 1, "targets": [item]}))
        plan = self.base / "plan.json"
        result = self.cli("cleanup.py", "preview", "--targets", src,
                          "--preferences", self.prefs, "--output", plan)
        return result, plan

    def make_app(self, path, bundle, version, binary=False):
        info = path / "Contents" / "Info.plist"
        info.parent.mkdir(parents=True)
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle,
            "CFBundleName": path.stem, "CFBundleShortVersionString": version,
            "CFBundleVersion": version}, fmt=plistlib.FMT_BINARY if binary else plistlib.FMT_XML))
        return path

    def test_preview_preserves_bytes_and_marks_no_owner_check(self):
        result, _ = self.preview()
        self.assertEqual((self.cache / "entry.bin").read_bytes(), b"original")
        self.assertEqual(result["targets"][0]["snapshot"]["status"], "ok")
        self.assertEqual(result["targets"][0]["owner_check"]["status"], "not_checked")
        self.assertEqual(result["targets"][0]["status"], "review")

    def test_symlink_target_is_blocked_without_traversal(self):
        link = self.base / "alias"
        link.symlink_to(self.cache, target_is_directory=True)
        result, _ = self.preview(path=str(link))
        self.assertEqual(result["targets"][0]["status"], "blocked")
        self.assertEqual((self.cache / "entry.bin").read_bytes(), b"original")

    def test_protected_child_prevents_parent_plan(self):
        self.config["protect_paths"] = [str(self.cache / "entry.bin")]
        self.prefs.write_text(json.dumps(self.config))
        result, _ = self.preview()
        self.assertEqual(result["targets"][0]["status"], "blocked")

    def test_protected_case_alias_is_not_treated_as_a_different_target(self):
        actual = self.base / "ProtectedCase"
        actual.mkdir()
        alias = self.base / "protectedcase"
        if not alias.exists():
            self.skipTest("Fixture volume is case sensitive")
        self.config["protect_paths"] = [str(actual)]
        self.prefs.write_text(json.dumps(self.config))
        result, _ = self.preview(path=str(alias))
        self.assertEqual(result["targets"][0]["status"], "blocked")

    def test_ancestor_link_swap_cannot_redirect_snapshot(self):
        parent = self.base / "parent"
        parent.mkdir()
        target = parent / "target"
        target.mkdir()
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "target").mkdir()
        (elsewhere / "target/private").write_text("must not traverse")
        original_resolve = Path.resolve
        swapped = False

        def swap(path, *args, **kwargs):
            nonlocal swapped
            resolved = original_resolve(path, *args, **kwargs)
            if path == target and not swapped:
                swapped = True
                parent.rename(self.base / "original-parent")
                parent.symlink_to(elsewhere, target_is_directory=True)
            return resolved

        with patch.object(Path, "resolve", swap):
            snap = common.snapshot(str(target))
        self.assertTrue(swapped)
        self.assertNotEqual(snap["status"], "ok")
        self.assertIsNone(snap["fingerprint"])

    def test_nested_targets_do_not_double_count(self):
        src = self.base / "targets.json"
        src.write_text(json.dumps({"version": 1, "targets": [
            {"id": "a", "path": str(self.cache), "kind": "cache", "reason": "fixture"},
            {"id": "b", "path": str(self.cache / "entry.bin"), "kind": "cache", "reason": "fixture"},
        ]}))
        r = self.cli("cleanup.py", "preview", "--targets", src,
                     "--preferences", self.prefs)
        self.assertTrue(all(t["status"] == "blocked" for t in r["targets"]))
        self.assertIsNone(r["total_target_allocated_bytes"])

    def test_file_change_invalidates_plan_even_when_parent_is_unchanged(self):
        _, plan = self.preview()
        (self.cache / "entry.bin").write_bytes(b"new contents")
        result = self.cli("cleanup.py", "verify", "--plan", plan,
                          "--preferences", self.prefs, expected=2)
        self.assertFalse(result["unchanged"])

    def test_symlink_swap_invalidates_plan(self):
        _, plan = self.preview()
        actual = self.base / "moved-cache"
        self.cache.rename(actual)
        self.cache.symlink_to(actual, target_is_directory=True)
        result = self.cli("cleanup.py", "verify", "--plan", plan,
                          "--preferences", self.prefs, expected=2)
        self.assertFalse(result["unchanged"])
        self.assertEqual((actual / "entry.bin").read_bytes(), b"original")

    def test_preferences_change_invalidates_previous_plan(self):
        _, plan = self.preview()
        self.config["protect_paths"] = [str(self.cache)]
        self.prefs.write_text(json.dumps(self.config))
        result = self.cli("cleanup.py", "verify", "--plan", plan,
                          "--preferences", self.prefs, expected=2)
        self.assertFalse(result["preferences_unchanged"])

    def test_unchanged_snapshot_can_be_revalidated(self):
        _, plan = self.preview()
        result = self.cli("cleanup.py", "verify", "--plan", plan,
                          "--preferences", self.prefs)
        self.assertTrue(result["unchanged"])

    def test_unverified_replacement_cannot_clear_old_app(self):
        old = self.make_app(self.base / "Old.app", "example.app", "1.0")
        new = self.make_app(self.base / "New.app", "example.app", "2.0")
        result, _ = self.preview(path=str(old), kind="obsolete_app",
            replacement={"path": str(new), "running_verified": False,
                         "dependencies_checked": True, "evidence": "license dialog"})
        self.assertEqual(result["targets"][0]["status"], "blocked")

    def test_inventory_reads_wrapped_and_binary_apps_and_applies_preferences(self):
        apps = self.base / "Applications"
        apps.mkdir()
        self.make_app(apps / "Resolve.app", "example.resolve", "21.0", binary=True)
        self.make_app(apps / "Photoshop.app", "example.adobe.photoshop", "27.0")
        self.make_app(apps / "Mobile.app.app" / "Wrapper" / "Mobile.app", "example.mobile", "6.4")
        before = (apps / "Resolve.app/Contents/Info.plist").read_bytes()
        r = self.cli("audit.py", "--apps-only", "--app-root", apps,
                     "--preferences", self.prefs)
        indexed = {x["bundle_id"]: x for x in r["applications"]}
        self.assertEqual(indexed["example.resolve"]["update_policy"]["mode"], "skip")
        self.assertEqual(indexed["example.adobe.photoshop"]["update_policy"]["mode"], "manager_only")
        self.assertEqual(indexed["example.mobile"]["version"], "6.4")
        self.assertEqual((apps / "Resolve.app/Contents/Info.plist").read_bytes(), before)

    def test_scan_skips_linked_app_root(self):
        apps = self.base / "Applications"
        apps.mkdir()
        real = self.make_app(self.base / "Elsewhere.app", "example.outside", "1")
        (apps / "Linked.app").symlink_to(real)
        r = self.cli("audit.py", "--apps-only", "--app-root", apps,
                     "--preferences", self.prefs)
        self.assertEqual(r["applications"], [])
        self.assertTrue(r["coverage_gaps"])

    def test_same_volume_move_is_recorded_without_reclaimed_space_claim(self):
        preview, plan = self.preview()
        dest = self.base / "quarantine"
        self.cache.rename(dest)
        results = self.base / "results.json"
        results.write_text(json.dumps({"version": 1, "results": [
            {"id": "cache", "action": "moved", "destination": str(dest), "detail": "fixture move"}]}))
        log = self.base / "actions.jsonl"
        r = self.cli("cleanup.py", "record", "--plan", plan, "--results", results, "--log", log)
        self.assertEqual(r["events"][0]["observed_status"], "moved_same_volume")
        self.assertEqual(r["events"][0]["target_bytes_removed"], 0)
        self.assertEqual(r["events"][0]["source_path_bytes_decrease"], preview["targets"][0]["snapshot"]["allocated_bytes"])
        self.assertIsNone(r["events"][0]["reclaimed_bytes"])

    def test_claimed_deletion_is_not_verified_when_target_remains(self):
        _, plan = self.preview()
        results = self.base / "results.json"
        results.write_text(json.dumps({"version": 1, "results": [{"id": "cache", "action": "removed"}]}))
        r = self.cli("cleanup.py", "record", "--plan", plan, "--results", results,
                     "--log", self.base / "actions.jsonl")
        self.assertEqual(r["events"][0]["observed_status"], "still_present")
        self.assertIsNone(r["events"][0]["reclaimed_bytes"])

    def test_output_does_not_overwrite_user_file(self):
        output = self.base / "existing.json"
        output.write_text("keep me")
        self.cli("audit.py", "--apps-only", "--app-root", self.base / "none",
                 "--preferences", self.prefs, "--output", output, expected=2)
        self.assertEqual(output.read_text(), "keep me")

    def test_command_timeout_and_failure_are_not_success(self):
        failed = common.command([sys.executable, "-c", "import sys; sys.stderr.write('unavailable'); sys.exit(7)"])
        self.assertEqual(failed["status"], "unknown")
        self.assertEqual(failed["returncode"], 7)
        timed = common.command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)
        self.assertEqual(timed["status"], "timeout")

    def test_snapshot_limit_is_unknown_instead_of_zero(self):
        snap = common.snapshot(str(self.cache), max_entries=1)
        self.assertEqual(snap["status"], "unknown")
        self.assertIsNone(snap["allocated_bytes"])
        self.assertIsNone(snap["fingerprint"])

    @unittest.skipIf(os.geteuid() == 0, "Root bypasses ordinary permission bits")
    def test_unreadable_directory_is_unknown_instead_of_zero(self):
        self.cache.chmod(0)
        try:
            snap = common.snapshot(str(self.cache))
            self.assertEqual(snap["status"], "unknown")
            self.assertIsNone(snap["allocated_bytes"])
        finally:
            self.cache.chmod(0o700)

    def test_malformed_xml_plist_is_a_coverage_gap(self):
        path = self.base / "Broken.app/Contents/Info.plist"
        path.parent.mkdir(parents=True)
        path.write_text('<?xml version="1.0"?><plist><dict>')
        result = self.cli("audit.py", "--apps-only", "--app-root", self.base / "Broken.app",
                          "--preferences", self.prefs)
        self.assertEqual(result["applications"], [])
        self.assertTrue(result["coverage_gaps"])

    def test_nested_link_is_recorded_without_reading_destination(self):
        (self.cache / "outside").symlink_to(self.base, target_is_directory=True)
        snap = common.snapshot(str(self.cache))
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["entry_count"], 3)
        self.assertEqual(snap["symlink_count"], 1)

    @unittest.skipUnless(sys.platform == "darwin", "OpenStep conversion uses macOS plutil")
    def test_openstep_plist_is_read_without_conversion_in_place(self):
        path = self.base / "Legacy.app/Contents/Info.plist"
        path.parent.mkdir(parents=True)
        contents = b'{ CFBundleIdentifier = "example.legacy"; CFBundleShortVersionString = "1.2"; }'
        path.write_bytes(contents)
        result = common.app_info(path.parents[1])
        self.assertEqual(result["version"], "1.2")
        self.assertEqual(path.read_bytes(), contents)

    def test_hardware_identifiers_are_removed_recursively(self):
        data = {"model": "Example", "serial_number": "private", "items": [
            {"platform_UUID": "private", "device_address": "private", "firmware": "1.0"}]}
        self.assertEqual(common.redact_hardware(data), {"model": "Example", "items": [{"firmware": "1.0"}]})

    def test_invalid_preference_does_not_silently_disable_protection(self):
        self.config["protect_paths"] = "wrong type"
        self.prefs.write_text(json.dumps(self.config))
        result = self.cli("audit.py", "--apps-only", "--preferences", self.prefs, expected=2)
        self.assertEqual(result["status"], "error")
        self.assertEqual((self.cache / "entry.bin").read_bytes(), b"original")

    def test_existing_non_log_file_cannot_be_corrupted_by_record(self):
        _, plan = self.preview()
        results = self.base / "results.json"
        results.write_text(json.dumps({"version": 1, "results": [{"id": "cache", "action": "skipped"}]}))
        logfile = self.base / "user-file.txt"
        logfile.write_text("existing user data\n")
        self.cli("cleanup.py", "record", "--plan", plan, "--results", results,
                 "--log", logfile, expected=2)
        self.assertEqual(logfile.read_text(), "existing user data\n")

    def test_log_append_keeps_previous_event_and_private_mode(self):
        _, plan = self.preview()
        results = self.base / "results.json"
        results.write_text(json.dumps({"version": 1, "results": [{"id": "cache", "action": "skipped"}]}))
        logfile = self.base / "actions.jsonl"
        first = self.cli("cleanup.py", "record", "--plan", plan, "--results", results, "--log", logfile)
        second = self.cli("cleanup.py", "record", "--plan", plan, "--results", results, "--log", logfile)
        events = [json.loads(line) for line in logfile.read_text().splitlines()]
        self.assertEqual(events, first["events"] + second["events"])
        self.assertEqual(logfile.stat().st_mode & 0o777, 0o600)

    def test_incomplete_log_line_is_not_glued_to_new_event(self):
        _, plan = self.preview()
        results = self.base / "results.json"
        results.write_text(json.dumps({"version": 1, "results": [{"id": "cache", "action": "skipped"}]}))
        logfile = self.base / "actions.jsonl"
        self.cli("cleanup.py", "record", "--plan", plan, "--results", results, "--log", logfile)
        partial = logfile.read_text().rstrip("\n")
        logfile.write_text(partial)
        self.cli("cleanup.py", "record", "--plan", plan, "--results", results, "--log", logfile, expected=2)
        self.assertEqual(logfile.read_text(), partial)

    def test_verified_replacement_changes_invalidate_plan(self):
        old = self.make_app(self.base / "Old.app", "example.app", "1.0")
        new = self.make_app(self.base / "New.app", "example.app", "2.0")
        result, plan = self.preview(path=str(old), kind="obsolete_app",
            replacement={"path": str(new), "running_verified": True,
                         "dependencies_checked": True, "evidence": "Fixture-only successful checks"})
        self.assertEqual(result["targets"][0]["status"], "review")
        (new / "Contents/new-file").write_text("changed")
        result = self.cli("cleanup.py", "verify", "--plan", plan,
                          "--preferences", self.prefs, expected=2)
        self.assertFalse(result["targets"][0]["replacement_unchanged"])

    def test_equal_numeric_versions_do_not_count_as_newer(self):
        old = self.make_app(self.base / "Old.app", "example.app", "1.0")
        new = self.make_app(self.base / "New.app", "example.app", "1.0.0")
        result, _ = self.preview(path=str(old), kind="obsolete_app",
            replacement={"path": str(new), "running_verified": True,
                         "dependencies_checked": True, "evidence": "Fixture"})
        self.assertEqual(result["targets"][0]["status"], "blocked")

    def test_hardlinked_targets_are_not_added_as_independent_bytes(self):
        linked = self.base / "linked.bin"
        os.link(self.cache / "entry.bin", linked)
        src = self.base / "targets.json"
        src.write_text(json.dumps({"version": 1, "targets": [
            {"id": "a", "path": str(self.cache / "entry.bin"), "kind": "cache", "reason": "fixture"},
            {"id": "b", "path": str(linked), "kind": "cache", "reason": "fixture"}]}))
        r = self.cli("cleanup.py", "preview", "--targets", src, "--preferences", self.prefs)
        self.assertIsNone(r["total_target_allocated_bytes"])


if __name__ == "__main__":
    unittest.main()
