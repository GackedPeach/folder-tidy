"""Copy-only integration and failure tests; all data lives in temporary folders."""
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import organiser_core as core


class OrganiserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "input"
        self.root.mkdir()
        self.history = self.base / "session.json"
        self.settings = core.load_settings(self.base / "no_config.json")

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def plan(self):
        return core.build_plan(core.scan(self.root, self.settings), self.root, self.settings)

    def run_plan(self, plan=None, **kwargs):
        return core.organise(self.plan() if plan is None else plan, self.root,
            history_path=self.history, output=core.get_output(self.root, self.settings), **kwargs)

    def test_category_copies_are_independent_and_originals_survive(self):
        original = self.write("holiday.jpg", b"some pixels")
        before = core.signature(original)
        plan = self.plan()
        self.assertEqual(plan[0]["category"], "Images")
        with patch("organiser_core.os.link", side_effect=AssertionError("No hard links")), \
             patch("organiser_core.shutil.move", side_effect=AssertionError("No moves")), \
             patch("organiser_core.Path.unlink", side_effect=AssertionError("No source deletion")):
            result = self.run_plan(plan)
        self.assertEqual(result["copied"], 1)
        self.assertEqual(core.signature(original), before)
        destination = Path(plan[0]["destination"])
        self.assertFalse(os.path.samefile(original, destination))
        destination.write_bytes(b"edited copy")
        self.assertEqual(original.read_bytes(), b"some pixels")

    def test_extension_sorting_handles_case_and_unusual_files(self):
        self.settings["organisation_mode"] = "Extension"
        self.write("clip.MP4", b"video")
        self.write("photo.jpg", b"image")
        self.write("README", b"no suffix")
        plan = self.plan()
        self.assertEqual({p["category"] for p in plan}, {"MP4", "JPG", "No Extension"})
        self.assertEqual(self.run_plan(plan)["copied"], 3)
        for item in plan:
            self.assertEqual(Path(item["source"]).read_bytes(), Path(item["destination"]).read_bytes())

    def test_modified_date_year_month_and_day(self):
        original = self.write("photo.jpg", b"photo")
        stamp = datetime(2021, 5, 17, 12, 30).timestamp()
        os.utime(original, (stamp, stamp))
        self.settings["organisation_mode"] = "Date Modified"
        for granularity, expected in [("Year", "2021"), ("Month", "2021/05 - May"), ("Day", "2021/05 - May/17")]:
            with self.subTest(granularity=granularity):
                self.settings["date_granularity"] = granularity
                plan = self.plan()
                self.assertEqual(plan[0]["category"], expected)
                self.assertEqual(self.run_plan(plan)["copied"], 1)
                self.assertEqual(core.signature(original)["mtime_ns"], int(stamp * 1e9))

    def test_creation_date_and_unavailable_creation_date_fallback(self):
        path = self.write("sample.txt", b"sample")
        self.settings.update(organisation_mode="Date Created", date_granularity="Day")
        snap = core.signature(path)
        snap["created_ns"] = int(datetime(2019, 3, 4, 12).timestamp() * 1e9)
        snap["mtime_ns"] = int(datetime(2022, 7, 8, 12).timestamp() * 1e9)
        self.assertEqual(core.category_for(path, self.settings, snap), "2019/03 - March/04")
        snap["created_ns"] = None
        self.assertEqual(core.category_for(path, self.settings, snap), "2022/07 - July/08")

    def test_destination_created_after_preview_is_never_overwritten(self):
        original = self.write("foo.txt", b"original")
        plan = self.plan()
        dest = Path(plan[0]["destination"])
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"do not overwrite")
        result = self.run_plan(plan)
        self.assertEqual((result["copied"], result["skipped"]), (0, 1))
        self.assertEqual(dest.read_bytes(), b"do not overwrite")
        self.assertEqual(original.read_bytes(), b"original")

    def test_stale_source_is_skipped(self):
        original = self.write("foo.txt", b"old")
        plan = self.plan()
        original.write_bytes(b"new and bigger")
        result = self.run_plan(plan)
        self.assertEqual((result["copied"], result["skipped"]), (0, 1))
        self.assertEqual(original.read_bytes(), b"new and bigger")

    def test_recursive_excludes_hidden_temporary_and_output(self):
        self.write("normal/file.pdf", b"okay")
        self.write(".git/config", b"hidden")
        self.write("node_modules/a.js", b"excluded")
        self.write("nested/.hidden/y.txt", b"hidden")
        self.write("Files Sorted/Images/old.jpg", b"already sorted")
        self.write("file.tmp", b"temporary")
        files = core.scan(self.root, self.settings)
        self.assertEqual([Path(x["source"]).name for x in files], ["file.pdf"])

    def test_symlinked_directory_not_traversed(self):
        self.write("real/f.txt", b"good")
        try:
            (self.root / "link").symlink_to(self.root / "real", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is unavailable")
        self.assertEqual(len(core.scan(self.root, self.settings)), 1)

    def test_include_extension_glob_and_size_range(self):
        self.write("keep_big.csv", b"x" * 1200)
        self.write("keep_small.csv", b"x")
        self.write("ignore_big.txt", b"x" * 1200)
        self.settings.update(include_extensions=[".csv"], filename_pattern="keep_*", min_size="1 KB", max_size="2 KB")
        results = core.scan(self.root, self.settings)
        self.assertEqual([Path(r["source"]).name for r in results], ["keep_big.csv"])

    def test_duplicate_hashes_dont_modify_files(self):
        a = self.write("a.pdf", b"same contents")
        b = self.write("b.pdf", b"same contents")
        self.write("c.pdf", b"very different")
        dup = core.find_duplicates(core.scan(self.root, self.settings))
        self.assertEqual(len(dup), 1)
        self.assertEqual(set(dup[0]["paths"]), {str(a), str(b)})
        self.assertEqual(a.read_bytes(), b"same contents")
        self.assertEqual(b.read_bytes(), b"same contents")

    def test_cancel_before_start_creates_nothing(self):
        original = self.write("a.docx", b"x")
        plan = self.plan()
        event = threading.Event()
        event.set()
        with self.assertRaises(core.Cancelled):
            core.scan(self.root, self.settings, cancel=event)
        result = self.run_plan(plan, cancel=event)
        self.assertTrue(result["cancelled"])
        self.assertEqual(list(self.root.iterdir()), [original])

    def test_custom_category_and_output_validation(self):
        self.write("thing.xyz", b"data")
        self.settings["custom_categories"] = {"My Custom": [".xyz"]}
        self.settings["output_folder"] = "Cleaned"
        plan = self.plan()
        self.assertEqual(plan[0]["category"], "My Custom")
        self.assertEqual(self.run_plan(plan)["copied"], 1)
        self.assertTrue((self.root / "Cleaned/My Custom/thing.xyz").exists())
        for bad in ("..", "../../outside", "CON", "a:b", "x\\y", "x/y"):
            self.settings["output_folder"] = bad
            with self.assertRaises(ValueError, msg=bad):
                core.scan(self.root, self.settings)

    def test_legacy_settings_migrate_without_changing_custom_preferences(self):
        saved = {"recursive": False, "output_folder": "Organised", "organisation_mode": "Date Modified",
                 "custom_categories": {"Stuff": [".abc"]}}
        p = self.base / "settings.json"
        p.write_text(json.dumps(saved), encoding="utf-8")
        settings = core.load_settings(p)
        self.assertFalse(settings["recursive"])
        self.assertEqual(settings["output_folder"], "Files Sorted")
        self.assertEqual(settings["date_granularity"], "Month")
        self.assertEqual(settings["custom_categories"], saved["custom_categories"])
        saved["output_folder"] = "My Copies"
        p.write_text(json.dumps(saved), encoding="utf-8")
        self.assertEqual(core.load_settings(p)["output_folder"], "My Copies")

    def test_deselection_skips_unselected_files(self):
        a = self.write("a.txt", b"a")
        b = self.write("b.txt", b"b")
        plan = self.plan()
        plan[0]["selected"] = False
        result = self.run_plan(plan)
        self.assertEqual(result["copied"], 1)
        self.assertTrue(a.exists() and b.exists())
        self.assertFalse(Path(plan[0]["destination"]).exists())

    def test_existing_category_symlink_rejected(self):
        outside = self.base / "unrelated"
        outside.mkdir()
        self.write("photo.png", b"photo")
        output = self.root / "Files Sorted"
        output.mkdir()
        try:
            (output / "Images").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is unavailable")
        self.assertEqual(self.plan(), [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_custom_extension_overrides_builtin_category(self):
        self.write("receipt.pdf", b"receipt")
        self.settings["custom_categories"] = {"Receipts": [".pdf"]}
        self.assertEqual(self.plan()[0]["category"], "Receipts")

    def test_camera_formats_and_unknown_extensions_are_included(self):
        for name in ("raw.dng", "camera.nef", "still.avif", "video.mts", "unknown.weird"):
            self.write(name, name.encode())
        groups = {Path(p["source"]).name: p["category"] for p in self.plan()}
        self.assertEqual(groups, {"raw.dng": "Images", "camera.nef": "Images", "still.avif": "Images",
                                  "video.mts": "Videos", "unknown.weird": "Others"})

    def test_many_name_collisions_use_unique_destinations(self):
        for index in range(100):
            self.write(f"folder{index:03}/same.txt", str(index).encode())
        plan = self.plan()
        self.assertEqual(len(plan), 100)
        self.assertEqual(len({p["destination"].casefold() for p in plan}), 100)
        self.assertTrue(any(Path(p["destination"]).name == "same_99.txt" for p in plan))

    def test_copy_failure_preserves_original_and_cleans_partial_output(self):
        original = self.write("file.txt", b"important")
        entry = self.plan()[0]
        with patch("organiser_core.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                core.copy_exclusive(original, entry["destination"], entry["snapshot"], self.root)
        self.assertEqual(original.read_bytes(), b"important")
        self.assertFalse(Path(entry["destination"]).exists())

    def test_cancel_during_copy_preserves_original(self):
        original = self.write("file.txt", b"important" * 200000)
        entry = self.plan()[0]
        event = threading.Event()
        real_fsync = os.fsync

        def cancel_after_flush(fd):
            real_fsync(fd)
            event.set()

        with patch("organiser_core.os.fsync", side_effect=cancel_after_flush):
            with self.assertRaises(core.Cancelled):
                core.copy_exclusive(original, entry["destination"], entry["snapshot"], self.root, event)
        self.assertEqual(original.read_bytes(), b"important" * 200000)
        self.assertFalse(Path(entry["destination"]).exists())

    def test_verification_failure_preserves_original(self):
        original = self.write("file.txt", b"important")
        entry = self.plan()[0]
        with patch("organiser_core.sha256_file", return_value="incorrect"):
            result = self.run_plan([entry])
        self.assertEqual(result["errors"], 1)
        self.assertEqual(original.read_bytes(), b"important")
        self.assertFalse(Path(entry["destination"]).exists())

    def test_source_change_during_verification_is_detected(self):
        original = self.write("file.txt", b"old")
        plan = self.plan()
        real_hash = core.sha256_file

        def change_source(*args, **kwargs):
            value = real_hash(*args, **kwargs)
            original.write_bytes(b"new content")
            return value

        with patch("organiser_core.sha256_file", side_effect=change_source):
            result = self.run_plan(plan)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(original.read_bytes(), b"new content")
        self.assertFalse(Path(plan[0]["destination"]).exists())

    def test_report_and_session_include_counts_paths_and_checksum(self):
        self.write("a.txt", b"hello")
        result = self.run_plan()
        report = Path(result["report"]).read_text(encoding="utf-8")
        self.assertIn("COPIED:", report)
        self.assertIn(hashlib.sha256(b"hello").hexdigest(), report)
        self.assertIn("Copied: 1", report)
        self.assertIn("Original files kept in place", report)
        self.assertEqual(core.load_history(self.history)["copied"], 1)
        self.assertEqual(result["bytes_copied"], 5)

    def test_repeated_runs_never_replace_existing_copies_or_reports(self):
        original = self.write("a.txt", b"hello")
        first = self.run_plan()
        second_plan = self.plan()
        self.assertEqual(len(second_plan), 1)
        self.assertEqual(Path(second_plan[0]["destination"]).name, "a_1.txt")
        second = self.run_plan(second_plan)
        self.assertNotEqual(first["report"], second["report"])
        self.assertEqual(original.read_bytes(), b"hello")

    def test_report_creation_failure_prevents_copying(self):
        original = self.write("a.txt", b"hello")
        plan = self.plan()
        with patch("organiser_core._open_report", side_effect=OSError("report cannot be opened")):
            with self.assertRaises(OSError):
                self.run_plan(plan)
        self.assertFalse(Path(plan[0]["destination"]).exists())
        self.assertEqual(original.read_bytes(), b"hello")

    def test_report_failure_stops_further_copies(self):
        self.write("a.txt", b"a")
        self.write("b.txt", b"b")
        plan = self.plan()
        real_open = core._open_report

        class FailingReport:
            def __init__(self, report):
                self.report = report

            def write(self, value):
                if value.startswith("COPIED:"):
                    raise OSError("report disk full")
                return self.report.write(value)

            def __getattr__(self, name):
                return getattr(self.report, name)

        def open_report(output):
            path, report = real_open(output)
            return path, FailingReport(report)

        with patch("organiser_core._open_report", side_effect=open_report):
            result = self.run_plan(plan)
        self.assertTrue(result["report_error"])
        self.assertEqual(result["copied"], 1)
        self.assertFalse(Path(plan[1]["destination"]).exists())
        self.assertTrue(all(Path(p["source"]).exists() for p in plan))

    def test_session_shortcut_failure_keeps_report_and_original(self):
        original = self.write("a.txt", b"hello")
        with patch("organiser_core.save_json_atomic", side_effect=OSError("cannot save session")):
            result = self.run_plan()
        self.assertTrue(result["history_error"])
        self.assertEqual(result["copied"], 1)
        self.assertTrue(Path(result["report"]).is_file())
        self.assertEqual(original.read_bytes(), b"hello")

    def test_insufficient_space_prevents_copying(self):
        original = self.write("a.txt", b"hello")
        with patch("organiser_core.shutil.disk_usage", return_value=shutil._ntuple_diskusage(10, 10, 0)):
            with self.assertRaisesRegex(OSError, "Not enough free space"):
                self.run_plan()
        self.assertEqual(list(self.root.iterdir()), [original])

    def test_cancellation_keeps_completed_copies_and_originals(self):
        self.write("a.txt", b"a")
        self.write("b.txt", b"b")
        plan = self.plan()
        event = threading.Event()

        def log(line):
            if line.startswith("COPIED:"):
                event.set()

        result = self.run_plan(plan, cancel=event, logger=log)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["copied"], 1)
        self.assertTrue(Path(plan[0]["destination"]).exists())
        self.assertTrue(all(Path(p["source"]).exists() for p in plan))

    def test_empty_selection_creates_nothing(self):
        original = self.write("a.txt", b"hello")
        plan = self.plan()
        plan[0]["selected"] = False
        self.assertEqual(self.run_plan(plan)["copied"], 0)
        self.assertEqual(list(self.root.iterdir()), [original])

    def test_destination_cannot_escape_the_output_folder(self):
        original = self.write("a.txt", b"hello")
        for destination in (self.root / "outside.txt", self.root / "Files Sorted/../a.txt"):
            plan = self.plan()
            plan[0]["destination"] = str(destination)
            self.assertEqual(self.run_plan(plan)["errors"], 1)
            self.assertEqual(original.read_bytes(), b"hello")

    def test_source_outside_root_is_never_copied(self):
        self.write("a.txt", b"hello")
        outside = self.base / "outside.txt"
        outside.write_bytes(b"outside")
        plan = self.plan()
        plan[0]["source"] = str(outside)
        plan[0]["snapshot"] = core.signature(outside)
        self.assertEqual(self.run_plan(plan)["errors"], 1)
        self.assertEqual(outside.read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()
