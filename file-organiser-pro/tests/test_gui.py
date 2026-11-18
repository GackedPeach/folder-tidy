"""Tk integration tests with a withdrawn window and isolated settings."""
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import file_organiser_pro as gui
import organiser_core as core


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        settings = core.load_settings(self.folder / "settings.json")
        for mocker in (
            patch.object(core, "load_settings", return_value=settings),
            patch.object(core, "load_history", return_value={"moves": []}),
            patch.object(core, "CONFIG_FILE", self.folder / "settings.json"),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.destroy_window)
        self.app = gui.FileOrganiser(self.root)

    def destroy_window(self):
        try:
            self.root.update_idletasks()
            for callback in self.root.tk.call("after", "info"):
                self.root.after_cancel(callback)
            self.root.destroy()
        except tk.TclError:
            pass

    def pump_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.002)
        self.assertTrue(predicate(), "Tk operation did not finish within the test timeout")

    def make_preview(self, count):
        self.app.planned_moves = [
            {"source": str(self.folder / f"file{i}.txt"), "category": "Documents",
             "destination": str(self.folder / "Organised" / f"file{i}.txt"),
             "size": i, "selected": True}
            for i in range(count)
        ]

    def test_large_preview_yields_to_event_loop(self):
        self.make_preview(10000)
        heartbeat = []
        self.root.after(0, lambda: heartbeat.append(True))
        self.app.populate_preview()
        self.assertTrue(self.app.busy)
        self.assertEqual(len(self.app.tree.get_children()), 200)
        self.pump_until(lambda: not self.app.busy)
        self.assertTrue(heartbeat)
        self.assertEqual(len(self.app.tree.get_children()), 10000)
        self.assertEqual(self.app.progress_text.cget("text"), "Preview ready")

    def test_setting_change_cancels_outdated_preview_render(self):
        self.make_preview(500)
        self.app.populate_preview()
        self.app.mode.set("Extension")
        self.pump_until(lambda: not self.app.busy)
        self.assertEqual(self.app.planned_moves, [])
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertIsNone(self.app.preview_context)

    def test_close_waits_for_worker_to_finish(self):
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def work(progress, logger, cancel):
            started.set()
            release.wait(3)
            return {"moved": 0, "skipped": 0, "errors": 0, "cancelled": True}

        self.app.start_job("organise", work)
        self.assertTrue(started.wait(1))
        self.assertFalse(self.app.worker.daemon)
        with patch.object(gui.messagebox, "askyesno", return_value=True), \
             patch.object(self.app, "finish_close") as finish:
            self.app.on_close()
            self.assertTrue(self.app.close_requested)
            self.assertTrue(self.app.cancel_event.is_set())
            self.root.update()
            finish.assert_not_called()
            self.assertTrue(self.root.winfo_exists())
            release.set()
            self.pump_until(lambda: finish.called)
        self.app.worker.join(1)
        self.assertFalse(self.app.worker.is_alive())

    def test_history_failure_keeps_recovery_log_available(self):
        self.app.close_requested = True
        with patch.object(gui.messagebox, "showwarning") as warning:
            self.app.on_job_done("organise", {"moved": 1, "skipped": 0, "errors": 1,
                "cancelled": False, "history_error": True}, None)
        warning.assert_called_once()
        self.assertFalse(self.app.close_requested)
        self.assertIn("undo history could not be saved", self.app.progress_text.cget("text"))
        self.assertIn("1 moved", self.app.summary.cget("text"))

    def test_event_poll_does_not_drain_unbounded_queue(self):
        self.app.events = queue.Queue()
        for index in range(1000):
            self.app.events.put(("progress", index, 1000, "file.txt"))
        self.app.poll_events()
        self.assertGreaterEqual(self.app.events.qsize(), 800)

    def test_close_reads_queued_history_warning_before_destroying_window(self):
        self.app.close_requested = True
        self.app.job_finished = False
        for index in range(1000):
            self.app.events.put(("progress", index, 1000, "file.txt"))
        self.app.events.put(("done", "organise", {"moved": 1, "skipped": 0,
            "errors": 1, "cancelled": False, "history_error": True}, None))
        with patch.object(self.app, "finish_close") as finish, \
             patch.object(gui.messagebox, "showwarning") as warning:
            self.app.poll_events()
            finish.assert_not_called()
            self.pump_until(lambda: warning.called)
            finish.assert_not_called()
        self.assertFalse(self.app.close_requested)


if __name__ == "__main__":
    unittest.main()
