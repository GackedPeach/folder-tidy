"""Run with: python -m unittest discover -s tests -v"""
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

import organiser_core as core


class OrganiserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / "history.json"
        self.settings = core.load_settings(self.root / "no_config.json")

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def plan(self):
        records = core.scan(self.root, self.settings)
        return core.build_plan(records, self.root, self.settings)

    def test_category_and_undo_after_history_reload(self):
        original = self.write("holiday.jpg", b"some pixels")
        planned = self.plan()
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]["category"], "Images")
        result = core.organise(planned, self.root, history_path=self.history)
        self.assertEqual(result["moved"], 1)
        self.assertFalse(original.exists())
        self.assertTrue((self.root / "Organised" / "Images" / "holiday.jpg").exists())
        self.assertEqual(len(core.load_history(self.history)["moves"]), 1)
        result = core.undo(self.history)
        self.assertEqual(result["restored"], 1)
        self.assertEqual(original.read_bytes(), b"some pixels")
        self.assertEqual(core.load_history(self.history)["moves"], [])

    def test_destination_created_after_preview_is_never_overwritten(self):
        original = self.write("foo.txt", b"original")
        plan = self.plan()
        dest = Path(plan[0]["destination"])
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"do not overwrite")
        result = core.organise(plan, self.root, history_path=self.history)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(dest.read_bytes(), b"do not overwrite")
        self.assertEqual(original.read_bytes(), b"original")

    def test_stale_source_is_skipped(self):
        original = self.write("foo.txt", b"old")
        plan = self.plan()
        original.write_bytes(b"new and bigger")
        result = core.organise(plan, self.root, history_path=self.history)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(original.read_bytes(), b"new and bigger")

    def test_undo_will_not_overwrite_occupied_original_path(self):
        original = self.write("doc.md", b"original")
        core.organise(self.plan(), self.root, history_path=self.history)
        original.write_bytes(b"new file")
        result = core.undo(self.history)
        self.assertEqual(result["restored"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(original.read_bytes(), b"new file")
        self.assertEqual(len(core.load_history(self.history)["moves"]), 1)

    def test_undo_will_not_revert_modified_destination(self):
        self.write("doc.md", b"old")
        plan = self.plan()
        core.organise(plan, self.root, history_path=self.history)
        dest = Path(plan[0]["destination"])
        dest.write_bytes(b"changed content")
        result = core.undo(self.history)
        self.assertEqual(result["restored"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_recursive_excludes_hidden_and_named_directories(self):
        self.settings["recursive"] = True
        self.write("normal/file.pdf", b"okay")
        self.write(".git/config", b"hidden")
        self.write("node_modules/a.js", b"excluded")
        self.write("nested/.hidden/y.txt", b"hidden")
        self.write("Organised/Images/old.jpg", b"already sorted")
        self.write("file.tmp", b"temp")
        files = core.scan(self.root, self.settings)
        self.assertEqual([Path(x["source"]).name for x in files], ["file.pdf"])

    def test_symlinked_directory_not_traversed(self):
        self.settings["recursive"] = True
        outside = self.root / "real"
        self.write("real/f.txt", b"good")
        try:
            (self.root / "link").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is unavailable")
        files = core.scan(self.root, self.settings)
        self.assertEqual(len(files), 1)
        self.assertEqual(Path(files[0]["source"]), outside / "f.txt")

    def test_include_extension_glob_and_size_range(self):
        self.write("keep_big.csv", b"x" * 1200)
        self.write("keep_small.csv", b"x")
        self.write("ignore_big.txt", b"x" * 1200)
        self.settings.update({"include_extensions": [".csv"], "filename_pattern": "keep_*", "min_size": "1 KB", "max_size": "2 KB"})
        results = core.scan(self.root, self.settings)
        self.assertEqual([Path(r["source"]).name for r in results], ["keep_big.csv"])

    def test_duplicate_hashes_dont_modify_files(self):
        a = self.write("a.pdf", b"same contents")
        b = self.write("b.pdf", b"same contents")
        self.write("c.pdf", b"very different")
        dup = core.find_duplicates(core.scan(self.root, self.settings))
        self.assertEqual(len(dup), 1)
        self.assertEqual(set(dup[0]["paths"]), {str(a), str(b)})
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_filter_and_plan_cancel(self):
        self.write("a.docx", b"x")
        event = threading.Event()
        event.set()
        with self.assertRaises(core.Cancelled):
            core.scan(self.root, self.settings, cancel=event)

    def test_custom_category_and_output_validation(self):
        self.write("thing.xyz", b"data")
        self.settings["custom_categories"] = {"My Custom": [".xyz"]}
        self.settings["output_folder"] = "Cleaned"
        self.assertEqual(self.plan()[0]["category"], "My Custom")
        for bad in ("..", "../../outside", "CON", "a:b", "x\\y", "x/y"):
            self.settings["output_folder"] = bad
            with self.assertRaises(ValueError, msg=bad):
                core.scan(self.root, self.settings)

    def test_compatibility_settings(self):
        saved = {"recursive": True, "ignored_extensions": [".log"], "organisation_mode": "Date Modified",
                 "custom_categories": {"Stuff": [".abc"]}}
        p = self.root / "settings.json"
        p.write_text(json.dumps(saved), encoding="utf-8")
        settings = core.load_settings(p)
        self.assertTrue(settings["recursive"])
        self.assertEqual(settings["custom_categories"], saved["custom_categories"])
        self.assertIn("last_folder", settings)
        self.assertIn("theme", settings)

    def test_failed_new_operation_keeps_previous_undo_history(self):
        self.write("first.txt", b"first")
        p1 = self.plan()
        core.organise(p1, self.root, history_path=self.history)
        original_journal = core.load_history(self.history)
        self.write("second.txt", b"second")
        p2 = self.plan()
        new_plan = [p for p in p2 if Path(p["source"]).name == "second.txt"]
        Path(new_plan[0]["destination"]).parent.mkdir(parents=True, exist_ok=True)
        Path(new_plan[0]["destination"]).write_bytes(b"collision")
        report = core.organise(new_plan, self.root, history_path=self.history)
        self.assertEqual(report["moved"], 0)
        self.assertEqual(core.load_history(self.history), original_journal)

    def test_cross_volume_fallback_never_overwrites(self):
        from unittest.mock import patch
        import errno
        original = self.write("big.txt", b"abc123" * 7000)
        entry = self.plan()[0]
        with patch("organiser_core.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
            result = core.organise([entry], self.root, history_path=self.history)
        self.assertEqual(result["moved"], 1)
        self.assertFalse(original.exists())
        self.assertEqual(Path(entry["destination"]).read_bytes(), b"abc123" * 7000)
        with patch("organiser_core.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
            back = core.undo(self.history)
        self.assertEqual(back["restored"], 1)
        self.assertEqual(original.read_bytes(), b"abc123" * 7000)

    def test_deselection_skips_unselected_files(self):
        a = self.write("a.txt", b"a")
        b = self.write("b.txt", b"b")
        plan = self.plan()
        plan[0]["selected"] = False
        result = core.organise(plan, self.root, history_path=self.history)
        self.assertEqual(result["moved"], 1)
        self.assertTrue(a.exists())
        self.assertFalse(b.exists())

    def test_existing_category_symlink_rejected(self):
        outside = self.root.parent / (self.root.name + "-unrelated")
        outside.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside.rmdir())
        self.write("photo.png", b"photo")
        output = self.root / "Organised"
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

    def test_date_plan_is_two_levels_and_safe(self):
        self.write("hello.pdf", b"date")
        self.settings["organisation_mode"] = "Date Modified"
        entry = self.plan()[0]
        dest = Path(entry["destination"])
        self.assertEqual(dest.parent.parent.parent.name, "Organised")
        self.assertEqual(dest.name, "hello.pdf")

    def test_collision_suffix_reservation(self):
        self.settings["recursive"] = True
        self.write("a/document.txt", b"one")
        self.write("b/document.txt", b"two")
        destinations = [p["destination"] for p in self.plan()]
        self.assertEqual(len(set(destinations)), 2)
        self.assertTrue(any(Path(p).name == "document_1.txt" for p in destinations))

    def test_move_does_not_read_destination_after_removing_original(self):
        original = self.write("file.txt", b"keep this content")
        entry = self.plan()[0]
        real_signature = core.signature

        def checked_signature(path):
            if Path(path) == Path(entry["destination"]) and not original.exists():
                raise OSError("Destination temporarily inaccessible after move")
            return real_signature(path)

        with patch("organiser_core.signature", side_effect=checked_signature):
            result = core.organise([entry], self.root, history_path=self.history)
        self.assertEqual(result["moved"], 1)
        self.assertFalse(original.exists())
        self.assertEqual(Path(entry["destination"]).read_bytes(), b"keep this content")
        self.assertEqual(core.undo(self.history)["restored"], 1)

    def test_copy_failure_preserves_original_and_removes_partial_copy(self):
        import errno
        original = self.write("file.txt", b"important")
        entry = self.plan()[0]
        with patch("organiser_core.os.link", side_effect=OSError(errno.EXDEV, "cross-device")), \
             patch("organiser_core.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                core.move_exclusive(original, entry["destination"], entry["snapshot"], self.root)
        self.assertEqual(original.read_bytes(), b"important")
        self.assertFalse(Path(entry["destination"]).exists())

    def test_cancel_during_copy_preserves_original(self):
        import errno
        original = self.write("file.txt", b"important" * 200000)
        entry = self.plan()[0]
        event = threading.Event()
        real_fsync = os.fsync

        def cancel_after_flush(fd):
            real_fsync(fd)
            event.set()

        with patch("organiser_core.os.link", side_effect=OSError(errno.EXDEV, "cross-device")), \
             patch("organiser_core.os.fsync", side_effect=cancel_after_flush):
            with self.assertRaises(core.Cancelled):
                core.move_exclusive(original, entry["destination"], entry["snapshot"], self.root, event)
        self.assertEqual(original.read_bytes(), b"important" * 200000)
        self.assertFalse(Path(entry["destination"]).exists())

    def test_unwritable_history_blocks_moves(self):
        original = self.write("file.txt", b"important")
        entry = self.plan()[0]
        with patch("organiser_core.save_history", side_effect=OSError("read-only history")):
            result = core.organise([entry], self.root, history_path=self.history)
        self.assertTrue(result["history_error"])
        self.assertEqual(result["moved"], 0)
        self.assertEqual(original.read_bytes(), b"important")

    def test_history_failure_stops_after_first_move_and_reports_it(self):
        self.write("a.txt", b"a")
        untouched = self.write("b.txt", b"b")
        plan = self.plan()
        real_save = core.save_history
        logs = []

        def fail_new_history(history, path):
            if history["moves"]:
                raise OSError("disk full")
            real_save(history, path)

        with patch("organiser_core.save_history", side_effect=fail_new_history):
            result = core.organise(plan, self.root, logger=logs.append, history_path=self.history)
        self.assertTrue(result["history_error"])
        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(Path(plan[0]["destination"]).read_bytes(), b"a")
        self.assertTrue(untouched.exists())
        self.assertTrue(any("HISTORY ERROR" in line and plan[0]["destination"] in line for line in logs))

    def test_prior_history_is_preserved_until_first_successful_move(self):
        original = self.write("first.txt", b"first")
        core.organise(self.plan(), self.root, history_path=self.history)
        previous = core.load_history(self.history)
        self.write("second.txt", b"second")
        plan = [p for p in self.plan() if Path(p["source"]).name == "second.txt"]

        def inspect_then_fail(*args, **kwargs):
            self.assertEqual(core.load_history(self.history), previous)
            raise core.FileChangedError("changed during move")

        with patch("organiser_core.move_exclusive", side_effect=inspect_then_fail):
            report = core.organise(plan, self.root, history_path=self.history)
        self.assertEqual(report["moved"], 0)
        self.assertEqual(core.load_history(self.history), previous)
        self.assertEqual(core.undo(self.history)["restored"], 1)
        self.assertEqual(original.read_bytes(), b"first")

    def test_unwritable_history_blocks_undo(self):
        original = self.write("file.txt", b"important")
        core.organise(self.plan(), self.root, history_path=self.history)
        with patch("organiser_core.save_history", side_effect=OSError("read-only history")):
            result = core.undo(self.history)
        self.assertTrue(result["history_error"])
        self.assertEqual(result["restored"], 0)
        self.assertFalse(original.exists())

    def test_undo_history_failure_counts_restored_file_and_stops(self):
        self.write("a.txt", b"a")
        self.write("b.txt", b"b")
        core.organise(self.plan(), self.root, history_path=self.history)
        real_save = core.save_history

        def fail_updated_history(history, path):
            if len(history["moves"]) < 2:
                raise OSError("disk full")
            real_save(history, path)

        with patch("organiser_core.save_history", side_effect=fail_updated_history):
            result = core.undo(self.history)
        self.assertTrue(result["history_error"])
        self.assertEqual(result["restored"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertTrue((self.root / "b.txt").exists())
        self.assertFalse((self.root / "a.txt").exists())

    def test_parent_traversal_cannot_escape_selected_root(self):
        with self.assertRaises(ValueError):
            core.safe_ancestors(self.root, self.root / ".." / "outside", create=True)

    def test_many_name_collisions_use_unique_destinations(self):
        self.settings["recursive"] = True
        for index in range(100):
            self.write(f"folder{index:03}/same.txt", str(index).encode())
        plan = self.plan()
        self.assertEqual(len(plan), 100)
        self.assertEqual(len({p["destination"].casefold() for p in plan}), 100)
        self.assertTrue(any(Path(p["destination"]).name == "same_99.txt" for p in plan))


if __name__ == "__main__":
    unittest.main()
