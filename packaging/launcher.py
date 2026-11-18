"""Native-app entry point, including an isolated release smoke check."""
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path

import tkinter as tk
import organiser_core as core
import file_organiser_pro as gui


def smoke_test(destination):
    result = {"version": core.APP_VERSION, "success": False}
    root = None
    try:
        with tempfile.TemporaryDirectory(prefix="file-organiser-smoke-") as folder:
            base = Path(folder)
            source = base / "input"
            source.mkdir()
            originals = {"clip.mp4": b"test video", "photo.jpg": b"test photo",
                         "nested/notes.txt": b"test document", "other.xyz": b"other"}
            for name, content in originals.items():
                item = source / name
                item.parent.mkdir(exist_ok=True)
                item.write_bytes(content)
            load_settings, load_history, organise = core.load_settings, core.load_history, core.organise
            core.CONFIG_FILE = base / "settings.json"
            core.load_settings = lambda *a, **k: load_settings(base / "settings.json")
            core.load_history = lambda *a, **k: load_history(base / "session.json")
            core.organise = lambda *a, **k: organise(*a, **k, history_path=base / "session.json")
            gui.messagebox.askyesno = lambda *a, **k: True

            def unexpected_dialog(title, message, **kwargs):
                raise RuntimeError(f"{title}: {message}")

            gui.messagebox.showerror = unexpected_dialog
            gui.messagebox.showwarning = unexpected_dialog
            root = tk.Tk()
            root.withdraw()
            app = gui.FileOrganiser(root)
            app.folder_path.set(str(source))

            def finish_job():
                deadline = time.monotonic() + 45
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.005)
                if app.busy:
                    raise RuntimeError("Smoke operation timed out")

            app.preview_copies()
            finish_job()
            if len(app.planned_copies) != len(originals):
                raise RuntimeError("Packaged preview did not find all fixture files")
            plan = list(app.planned_copies)
            app.organise_files()
            finish_job()
            session = load_history(base / "session.json")
            if session.get("copied") != len(originals) or session.get("errors"):
                raise RuntimeError(f"Packaged copy operation failed: {session}")
            for name, content in originals.items():
                if (source / name).read_bytes() != content:
                    raise RuntimeError("An original changed")
            for item in plan:
                original, copied = Path(item["source"]), Path(item["destination"])
                if copied.read_bytes() != original.read_bytes() or copied.samefile(original):
                    raise RuntimeError("Output is not an independent copy")
            if not Path(session["report"]).is_file():
                raise RuntimeError("Copy report is missing")
            result.update(success=True, copied=len(originals), tk_version=root.tk.call("info", "patchlevel"))
            for callback in root.tk.call("after", "info"):
                root.after_cancel(callback)
            root.destroy()
            root = None
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        Path(destination).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        sys.exit(smoke_test(sys.argv[2]))
    root = tk.Tk()
    gui.FileOrganiser(root)
    root.mainloop()
