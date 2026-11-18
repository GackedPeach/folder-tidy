"""File Organiser Pro 1.1.1 — local-only Tkinter desktop interface.

Run: python file_organiser_pro.py
Standard library only. Python 3.10+ recommended.
"""
from __future__ import annotations

import copy
import csv
import os
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import organiser_core as core


class FileOrganiser:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{core.APP_NAME} {core.APP_VERSION}")
        root.geometry("1180x845")
        root.minsize(930, 680)
        self.settings = core.load_settings()

        self.folder_path = tk.StringVar(value=str(self.settings.get("last_folder", "")))
        self.recursive = tk.BooleanVar(value=self.settings["recursive"])
        self.skip_hidden = tk.BooleanVar(value=self.settings["skip_hidden"])
        self.mode = tk.StringVar(value=self.settings["organisation_mode"])
        self.output_folder = tk.StringVar(value=self.settings["output_folder"])
        self.ignore_text = tk.StringVar(value=", ".join(self.settings["ignore_patterns"]))
        self.ignore_extensions = tk.StringVar(value=", ".join(self.settings["ignored_extensions"]))
        self.exclude_dirs = tk.StringVar(value=", ".join(self.settings["excluded_directories"]))
        self.include_extensions = tk.StringVar(value=", ".join(self.settings["include_extensions"]))
        self.filename_pattern = tk.StringVar(value=str(self.settings["filename_pattern"]))
        self.min_size = tk.StringVar(value=str(self.settings["min_size"]))
        self.max_size = tk.StringVar(value=str(self.settings["max_size"]))
        self.theme_var = tk.StringVar(value=self.settings["theme"])

        self.planned_moves: list[dict] = []
        self.preview_context = None
        self.pending_preview_context = None
        self.scanned_files: list[dict] = []
        self.log_entries: list[dict] = []
        self.busy = False
        self.job_name = ""
        self.events = queue.Queue()
        self.cancel_event = None
        self.worker = None
        self.job_finished = True
        self.close_requested = False
        self.render_generation = 0
        self.action_buttons = []
        self.editable_widgets = []
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.setup_ui()
        self.apply_theme()
        self.bind_changes()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(80, self.poll_events)
        if self.folder_path.get() and Path(self.folder_path.get()).is_dir():
            self.summary.configure(text=f"Previous folder: {self.folder_path.get()}. Select Scan or Preview.")
        self.update_undo_button()

    def bind_changes(self):
        relevant = [self.folder_path, self.recursive, self.skip_hidden, self.mode,
                    self.output_folder, self.ignore_text, self.ignore_extensions,
                    self.exclude_dirs, self.include_extensions, self.filename_pattern,
                    self.min_size, self.max_size]
        for var in relevant:
            var.trace_add("write", self.invalidate_plan)
        self.theme_var.trace_add("write", lambda *_: self.apply_theme())

    def settings_snapshot(self) -> dict:
        value = copy.deepcopy(self.settings)
        value.update({
            "recursive": self.recursive.get(), "skip_hidden": self.skip_hidden.get(),
            "organisation_mode": self.mode.get(), "output_folder": self.output_folder.get(),
            "ignore_patterns": core.parse_list(self.ignore_text.get()),
            "ignored_extensions": core.normalize_extensions(core.parse_list(self.ignore_extensions.get())),
            "excluded_directories": core.parse_list(self.exclude_dirs.get()),
            "include_extensions": core.normalize_extensions(core.parse_list(self.include_extensions.get())),
            "filename_pattern": self.filename_pattern.get(), "min_size": self.min_size.get(),
            "max_size": self.max_size.get(), "theme": self.theme_var.get(),
            "last_folder": self.folder_path.get().strip(),
        })
        return value

    def save_settings(self):
        self.settings = self.settings_snapshot()
        try:
            core.save_json_atomic(core.CONFIG_FILE, self.settings)
        except OSError as exc:
            self.log(f"SETTINGS ERROR: {exc}")

    def validate_input(self):
        settings = self.settings_snapshot()
        root = core.get_root(self.folder_path.get())
        core.get_output(root, settings)
        core.validate_filters(settings)
        core.categories_for(settings)
        return root, settings

    def setup_ui(self):
        header = ttk.Frame(self.root, padding=(18, 12))
        header.pack(fill="x")
        ttk.Label(header, text="FILE ORGANISER PRO", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"v{core.APP_VERSION}   •   local-first / preview-first", style="Sub.TLabel").pack(side="left", padx=16)
        ttk.Label(header, text="Theme:").pack(side="right", padx=(5, 0))
        theme = ttk.Combobox(header, textvariable=self.theme_var, values=["Dark", "Light"], state="readonly", width=7)
        theme.pack(side="right")
        self.editable_widgets.append((theme, "readonly"))

        folder_frame = ttk.LabelFrame(self.root, text=" Folder Selection ", padding=9)
        folder_frame.pack(fill="x", padx=18, pady=(0, 5))
        entry = ttk.Entry(folder_frame, textvariable=self.folder_path)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.editable_widgets.append((entry, "normal"))
        self.add_button(folder_frame, "Browse…", self.browse_folder, side="left")
        self.add_button(folder_frame, "Open Folder", self.open_folder, side="left")

        settings_box = ttk.LabelFrame(self.root, text=" Organisation Settings ", padding=9)
        settings_box.pack(fill="x", padx=18, pady=4)
        row1 = ttk.Frame(settings_box)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Method:").pack(side="left")
        method = ttk.Combobox(row1, textvariable=self.mode, values=core.MODES, state="readonly", width=18)
        method.pack(side="left", padx=(5, 16))
        self.editable_widgets.append((method, "readonly"))
        ttk.Label(row1, text="Output folder:").pack(side="left")
        out_entry = ttk.Entry(row1, textvariable=self.output_folder, width=21)
        out_entry.pack(side="left", padx=(5, 18))
        self.editable_widgets.append((out_entry, "normal"))
        self.add_check(row1, "Include subfolders", self.recursive)
        self.add_check(row1, "Skip hidden", self.skip_hidden)

        filters = ttk.LabelFrame(self.root, text=" Filters / Exclusions (comma-separated where applicable) ", padding=9)
        filters.pack(fill="x", padx=18, pady=4)
        r = ttk.Frame(filters)
        r.pack(fill="x", pady=2)
        self.filter_field(r, "Ignore names/patterns:", self.ignore_text, grow=True)
        self.filter_field(r, "Ignore extensions:", self.ignore_extensions, width=20)
        r = ttk.Frame(filters)
        r.pack(fill="x", pady=2)
        self.filter_field(r, "Exclude directories:", self.exclude_dirs, grow=True)
        self.filter_field(r, "Only extensions:", self.include_extensions, width=20)
        r = ttk.Frame(filters)
        r.pack(fill="x", pady=2)
        self.filter_field(r, "Filename glob:", self.filename_pattern, width=21)
        self.filter_field(r, "Min size:", self.min_size, width=11)
        self.filter_field(r, "Max size:", self.max_size, width=11)
        ttk.Label(r, text="e.g. *.pdf   /   100 KB   /   2 GB", style="Sub.TLabel").pack(side="left", padx=8)

        actions = ttk.Frame(self.root, padding=(18, 7))
        actions.pack(fill="x")
        for label, cmd in [
            ("Scan Files", self.scan_folder), ("Preview Moves", self.preview_moves),
            ("Organise Selected", self.organise_files), ("Undo Last", self.undo_last),
            ("Find Duplicates", self.find_duplicates), ("Custom Categories", self.edit_categories),
        ]:
            b = self.add_button(actions, label, cmd, side="left", style="Action.TButton")
            if label == "Undo Last":
                self.undo_btn = b
        self.cancel_btn = ttk.Button(actions, text="Cancel Job", command=self.cancel_job, state="disabled")
        self.cancel_btn.pack(side="right", padx=2)

        progress_frame = ttk.Frame(self.root, padding=(18, 0, 18, 7))
        progress_frame.pack(fill="x")
        self.summary = ttk.Label(progress_frame, text="Select a folder to get started.", style="Summary.TLabel")
        self.summary.pack(anchor="w", pady=(2, 4))
        self.progress = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress.pack(fill="x")
        self.progress_text = ttk.Label(progress_frame, text="Ready", style="Sub.TLabel")
        self.progress_text.pack(anchor="w", pady=(3, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        preview_tab = ttk.Frame(notebook, padding=7)
        notebook.add(preview_tab, text="Move Preview")
        selection_bar = ttk.Frame(preview_tab)
        selection_bar.pack(fill="x", pady=(0, 6))
        for label, cmd in [("Include All", lambda: self.select_all(True)),
                           ("Exclude All", lambda: self.select_all(False)),
                           ("Toggle Highlighted", self.toggle_highlighted)]:
            ttk.Button(selection_bar, text=label, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(selection_bar, text="Double-click a row or highlight rows to toggle inclusion.",
                  style="Sub.TLabel").pack(side="right")
        self.tree = self.make_tree(preview_tab,
                                   ("include", "name", "category", "destination", "size"),
                                   ("Use", "File Name", "Group", "Destination", "Size"),
                                   (52, 210, 140, 505, 94))
        self.tree.bind("<Double-1>", self.on_preview_double_click)
        self.tree.bind("<space>", lambda _: self.toggle_highlighted())

        duplicate_tab = ttk.Frame(notebook, padding=7)
        notebook.add(duplicate_tab, text="Duplicates (read-only)")
        ttk.Label(duplicate_tab, text="Matching SHA-256 hashes. No files are removed automatically.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 6))
        self.duplicates_tree = self.make_tree(duplicate_tab,
                                              ("group", "hash", "size", "path"),
                                              ("Group", "SHA-256 prefix", "Size", "File path"),
                                              (70, 135, 100, 700))

        log_tab = ttk.Frame(notebook, padding=7)
        notebook.add(log_tab, text="Activity Log")
        log_buttons = ttk.Frame(log_tab)
        log_buttons.pack(side="bottom", fill="x", pady=(7, 0))
        ttk.Button(log_buttons, text="Export TXT / CSV…", command=self.export_log).pack(side="left")
        ttk.Button(log_buttons, text="Clear Log", command=self.clear_log).pack(side="right")
        text_frame = ttk.Frame(log_tab)
        text_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(text_frame, font=("Consolas", 9), wrap="word", state="disabled",
                               borderwidth=0, highlightthickness=0)
        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def add_button(self, parent, label, command, side="left", style=None):
        btn = ttk.Button(parent, text=label, command=command, style=style or "TButton")
        btn.pack(side=side, padx=(0, 6))
        self.action_buttons.append(btn)
        return btn

    def add_check(self, parent, text, var):
        c = ttk.Checkbutton(parent, text=text, variable=var)
        c.pack(side="left", padx=(0, 15))
        self.editable_widgets.append((c, "normal"))

    def filter_field(self, parent, label, var, width=24, grow=False):
        ttk.Label(parent, text=label).pack(side="left", padx=(0, 4))
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.pack(side="left", padx=(0, 14), fill="x" if grow else None, expand=grow)
        self.editable_widgets.append((entry, "normal"))

    @staticmethod
    def make_tree(parent, columns, headings, widths):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="extended")
        for col, label, width in zip(columns, headings, widths):
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="center" if col in ("include", "group", "size") else "w",
                        stretch=col in ("path", "destination", "name"))
        scroll_y = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def apply_theme(self):
        dark = self.theme_var.get() == "Dark"
        bg, fg = ("#20252d", "#e6edf5") if dark else ("#f5f7fa", "#20252d")
        panel, field = ("#2b323c", "#161b22") if dark else ("#e7ebef", "#ffffff")
        selected = "#2563a8" if dark else "#bbd8f9"
        self.root.configure(background=bg)
        s = self.style
        s.configure("TFrame", background=bg)
        s.configure("TLabelframe", background=bg, foreground=fg)
        s.configure("TLabelframe.Label", background=bg, foreground=fg)
        s.configure("TLabel", background=bg, foreground=fg)
        s.configure("Title.TLabel", background=bg, foreground=fg, font=("Segoe UI", 20, "bold"))
        s.configure("Summary.TLabel", background=bg, foreground=fg, font=("Segoe UI", 10, "bold"))
        s.configure("Sub.TLabel", background=bg, foreground="#aeb8c6" if dark else "#5b6573")
        s.configure("TButton", background=panel, foreground=fg, padding=5)
        s.map("TButton", background=[("active", "#3a4d61" if dark else "#d4dce4")],
              foreground=[("disabled", "#77818f")])
        s.configure("Action.TButton", font=("Segoe UI", 9, "bold"), padding=7)
        s.configure("TCheckbutton", background=bg, foreground=fg)
        s.map("TCheckbutton", background=[("active", bg)])
        s.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg)
        s.configure("TCombobox", fieldbackground=field, foreground=fg, background=panel,
                    arrowcolor=fg)
        s.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", fg)])
        s.configure("Treeview", fieldbackground=field, background=field, foreground=fg, rowheight=25)
        s.configure("Treeview.Heading", background=panel, foreground=fg, font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", selected)], foreground=[("selected", fg)])
        s.configure("TNotebook", background=bg)
        s.configure("TNotebook.Tab", background=panel, foreground=fg, padding=(11, 5))
        s.map("TNotebook.Tab", background=[("selected", field)])
        s.configure("Horizontal.TProgressbar", background="#4b9ef9", troughcolor=panel)
        self.log_box.configure(bg=field, fg=fg, insertbackground=fg)
        self.tree.tag_configure("excluded", foreground="#8a929d" if dark else "#8b9198")

    def invalidate_plan(self, *_):
        self.render_generation += 1
        self.preview_context = None
        if not self.planned_moves:
            return
        self.planned_moves = []
        self.clear_tree(self.tree)
        if not self.busy:
            self.summary.configure(text="Settings changed. Generate a new preview before organising.")

    @staticmethod
    def clear_tree(tree):
        children = tree.get_children()
        if children:
            tree.delete(*children)

    def log(self, message: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = str(message).split(":", 1)[0] if ":" in str(message) else "INFO"
        self.log_entries.append({"timestamp": now, "status": status, "message": str(message)})
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{now}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_entries.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def export_log(self):
        if not self.log_entries:
            messagebox.showinfo("Export Activity", "No activity has been logged yet.")
            return
        filename = filedialog.asksaveasfilename(title="Export activity log", defaultextension=".txt",
                                                filetypes=[("Text file", "*.txt"), ("CSV file", "*.csv")])
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8", newline="") as f:
                if Path(filename).suffix.lower() == ".csv":
                    writer = csv.DictWriter(f, fieldnames=["timestamp", "status", "message"])
                    writer.writeheader()
                    writer.writerows(self.log_entries)
                else:
                    for item in self.log_entries:
                        f.write(f"[{item['timestamp']}] {item['message']}\n")
            self.log(f"EXPORTED: {filename}")
        except OSError as exc:
            messagebox.showerror("Export Failed", str(exc))

    def browse_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder_path.get() or str(Path.home()))
        if selected:
            self.folder_path.set(selected)
            self.save_settings()
            self.log(f"Selected folder: {selected}")
            self.scan_folder()

    def open_folder(self):
        try:
            folder = core.get_root(self.folder_path.get())
            system = platform.system()
            if system == "Windows":
                os.startfile(str(folder))
            elif system == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except (ValueError, OSError, AttributeError) as exc:
            messagebox.showerror("Open Folder", str(exc))

    def edit_categories(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Custom Categories")
        dialog.geometry("540x430")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="One category per line: Category: .ext, .ext").pack(pady=10)
        editor = tk.Text(dialog, font=("Consolas", 10), height=14)
        editor.pack(fill="both", expand=True, padx=12)
        for name, exts in self.settings.get("custom_categories", {}).items():
            editor.insert("end", f"{name}: {', '.join(exts)}\n")

        def save():
            custom = {}
            try:
                for line in editor.get("1.0", "end").splitlines():
                    if not line.strip():
                        continue
                    if ":" not in line:
                        raise ValueError(f"Missing ':' on line: {line}")
                    name, extensions = line.split(":", 1)
                    name = core.validate_component(name.strip())
                    custom[name] = core.normalize_extensions(core.parse_list(extensions))
                self.settings["custom_categories"] = custom
                self.invalidate_plan()
                self.save_settings()
                self.log("Custom categories updated.")
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("Invalid Category", str(exc), parent=dialog)

        ttk.Button(dialog, text="Save Categories", command=save).pack(pady=10)

    def set_busy(self, busy: bool):
        self.busy = busy
        for btn in self.action_buttons:
            btn.configure(state="disabled" if busy else "normal")
        for widget, original in self.editable_widgets:
            widget.configure(state="disabled" if busy else original)
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        if not busy:
            self.update_undo_button()

    def update_undo_button(self):
        if not self.busy:
            self.undo_btn.configure(state="normal" if core.load_history().get("moves") else "disabled")

    def start_job(self, name: str, work):
        if self.busy:
            return
        self.cancel_event = threading.Event()
        self.job_finished = False
        self.job_name = name
        self.set_busy(True)
        self.progress.configure(mode="indeterminate" if name in ("scan", "preview", "duplicates") else "determinate",
                                value=0, maximum=100)
        if name in ("scan", "preview", "duplicates"):
            self.progress.start(10)
        self.summary.configure(text=f"{name.capitalize()} running…")
        self.progress_text.configure(text="Starting…")

        def worker():
            last_report = 0.0

            def report(current, total, filename):
                nonlocal last_report
                now = time.monotonic()
                if now - last_report >= 0.05 or current == total:
                    self.events.put(("progress", current, total, filename))
                    last_report = now

            def write_log(line):
                self.events.put(("log", line))

            try:
                result = work(report, write_log, self.cancel_event)
                self.events.put(("done", name, result, None))
            except core.Cancelled:
                self.events.put(("done", name, None, "Cancelled"))
            except Exception as exc:
                self.events.put(("done", name, None, str(exc)))

        self.worker = threading.Thread(target=worker, name=f"FileOrganiser-{name}", daemon=False)
        self.worker.start()

    def cancel_job(self):
        if self.busy and self.cancel_event:
            self.cancel_event.set()
            self.progress_text.configure(text="Cancellation requested; finishing current safe boundary…")
            self.cancel_btn.configure(state="disabled")

    def poll_events(self):
        try:
            # Yield to Tk regularly even when a large operation fills the queue.
            deadline = time.monotonic() + 0.015
            for _ in range(200):
                if time.monotonic() >= deadline:
                    break
                event = self.events.get_nowait()
                if event[0] == "log":
                    self.log(event[1])
                elif event[0] == "progress":
                    _, current, total, filename = event
                    if total is not None:
                        if str(self.progress.cget("mode")) == "indeterminate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate")
                        self.progress.configure(maximum=max(total, 1), value=current)
                        self.progress_text.configure(text=f"Processed {current} / {total}  •  Remaining {max(total-current,0)}  •  {filename}")
                    else:
                        self.progress_text.configure(text=f"Scanned {current} entries  •  {filename}")
                elif event[0] == "done":
                    _, name, result, error = event
                    self.job_finished = True
                    self.progress.stop()
                    self.set_busy(False)
                    self.on_job_done(name, result, error)
        except queue.Empty:
            pass
        if self.close_requested and self.job_finished and not (self.worker and self.worker.is_alive()):
            self.finish_close()
            return
        try:
            self.root.after(80, self.poll_events)
        except tk.TclError:
            pass

    def on_job_done(self, name, result, error):
        if error:
            self.summary.configure(text=f"{name.capitalize()}: {error}")
            self.log(f"JOB: {name}: {error}")
            if error != "Cancelled":
                messagebox.showerror(f"{name.capitalize()} Failed", error)
            return
        if isinstance(result, dict) and result.get("history_error"):
            messagebox.showwarning("Undo History Could Not Be Saved",
                "The operation stopped because undo history could not be saved.\n\n"
                "Completed moves are included in the activity log. Export that log "
                "before closing; the last move may need to be restored manually.")
            # Keep the app open so the recovery paths can be exported.
            self.close_requested = False
        if self.close_requested:
            return
        if name == "scan":
            self.scanned_files = result
            self.planned_moves.clear()
            self.clear_tree(self.tree)
            size = sum(item["snapshot"]["size"] for item in result)
            self.summary.configure(text=f"Scan complete: {len(result)} files  •  {core.format_size(size)}")
        elif name == "preview":
            self.scanned_files, self.planned_moves = result
            self.preview_context = self.pending_preview_context
            self.populate_preview()
        elif name == "duplicates":
            self.populate_duplicates(result)
        elif name == "organise":
            self.invalidate_plan()
            self.scanned_files = []
            self.summary.configure(text=f"Organised: {result['moved']} moved  •  {result['skipped']} skipped  •  {result['errors']} errors"
                                        + ("  •  cancelled" if result["cancelled"] else ""))
            self.log(f"RESULT: {self.summary.cget('text')}")
            self.update_undo_button()
        elif name == "undo":
            self.invalidate_plan()
            self.scanned_files = []
            self.summary.configure(text=f"Undo: {result['restored']} restored  •  {result['skipped']} skipped  •  {result['errors']} errors"
                                        + ("  •  cancelled" if result["cancelled"] else ""))
            self.log(f"RESULT: {self.summary.cget('text')}")
            self.update_undo_button()
        if isinstance(result, dict) and result.get("history_error"):
            self.progress_text.configure(text="Stopped: undo history could not be saved. See Activity Log.")
        elif name != "preview":
            self.progress_text.configure(text="Stopped safely" if isinstance(result, dict) and result.get("cancelled") else "Finished")

    def scan_folder(self):
        try:
            root, settings = self.validate_input()
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return
        self.start_job("scan", lambda p, l, c: core.scan(root, settings, p, l, c))

    def preview_moves(self):
        try:
            root, settings = self.validate_input()
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return

        def run(progress, logger, cancel):
            records = core.scan(root, settings, progress, logger, cancel)
            return records, core.build_plan(records, root, settings, logger, cancel)

        self.planned_moves = []
        self.preview_context = None
        self.pending_preview_context = (str(root), copy.deepcopy(settings))
        self.clear_tree(self.tree)
        self.start_job("preview", run)

    def populate_preview(self):
        self.render_generation += 1
        generation = self.render_generation
        self.clear_tree(self.tree)
        self.set_busy(True)
        self.cancel_btn.configure(state="disabled")

        def insert_batch(start=0):
            if generation != self.render_generation or self.close_requested:
                self.set_busy(False)
                return
            stop = min(start + 200, len(self.planned_moves))
            for index in range(start, stop):
                item = self.planned_moves[index]
                self.tree.insert("", "end", iid=f"p{index}", values=("✓" if item["selected"] else "–",
                    Path(item["source"]).name, item["category"], item["destination"], core.format_size(item["size"])),
                    tags=() if item["selected"] else ("excluded",))
            if stop < len(self.planned_moves):
                self.progress_text.configure(text=f"Loading preview: {stop} / {len(self.planned_moves)}")
                self.root.after(1, lambda: insert_batch(stop))
            else:
                self.set_busy(False)
                self.refresh_selection_summary()
                self.progress_text.configure(text="Preview ready")

        insert_batch()

    def refresh_selection_summary(self):
        included = [p for p in self.planned_moves if p["selected"]]
        total_size = sum(p["size"] for p in included)
        self.summary.configure(text=f"Preview: {len(included)} selected / {len(self.planned_moves)} files  •  {core.format_size(total_size)}")

    def select_all(self, checked):
        if self.busy:
            return
        for item in self.planned_moves:
            item["selected"] = checked
        self.populate_preview()

    def toggle_highlighted(self):
        if self.busy:
            return
        for row in self.tree.selection():
            index = int(row[1:])
            if index < len(self.planned_moves):
                obj = self.planned_moves[index]
                obj["selected"] = not obj["selected"]
                self.tree.item(row, values=("✓" if obj["selected"] else "–", Path(obj["source"]).name,
                                   obj["category"], obj["destination"], core.format_size(obj["size"])),
                               tags=() if obj["selected"] else ("excluded",))
        self.refresh_selection_summary()

    def on_preview_double_click(self, event):
        if self.busy:
            return
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.toggle_highlighted()

    def organise_files(self):
        if self.busy:
            return
        if not self.planned_moves:
            messagebox.showinfo("Preview Required", "Generate a preview and select files before organising.")
            return
        chosen = sum(bool(p["selected"]) for p in self.planned_moves)
        if not chosen:
            messagebox.showinfo("Nothing Selected", "Select at least one file in the preview.")
            return
        # Checking again prevents execution with changed input configuration.
        try:
            root, settings = self.validate_input()
            if self.preview_context != (str(root), settings):
                raise ValueError("Folder or settings changed; recreate the preview.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return
        prior = len(core.load_history().get("moves", []))
        notice = (f"Move {chosen} selected files?\n\n"
                  "Existing destination files will never be replaced.\n"
                  "Changed or missing sources will be skipped.\n"
                  "Cancellation stops at a safe file boundary.")
        if prior:
            notice += f"\n\nNote: This replaces undo history for {prior} earlier moves."
        if not messagebox.askyesno("Confirm Organisation", notice):
            return
        plan = copy.deepcopy(self.planned_moves)
        self.start_job("organise", lambda p, l, c: core.organise(plan, root, p, l, c))

    def undo_last(self):
        history = core.load_history()
        count = len(history.get("moves", []))
        if not count:
            messagebox.showinfo("Undo", "There are no moves to undo.")
            return
        msg = (f"Try to restore {count} files from the most recent operation?\n\n"
               "Modified files and occupied original locations will be skipped.\n"
               "The undo journal is updated after each successful restoration.")
        if not messagebox.askyesno("Confirm Undo", msg):
            return
        self.start_job("undo", lambda p, l, c: core.undo(progress=p, logger=l, cancel=c))

    def find_duplicates(self):
        try:
            root, settings = self.validate_input()
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return

        def run(progress, logger, cancel):
            records = core.scan(root, settings, progress, logger, cancel)
            return core.find_duplicates(records, progress, logger, cancel)

        self.start_job("duplicates", run)

    def populate_duplicates(self, groups):
        self.clear_tree(self.duplicates_tree)
        extra = 0
        for index, group in enumerate(groups, 1):
            extra += (len(group["paths"]) - 1) * group["size"]
            for path in group["paths"]:
                self.duplicates_tree.insert("", "end", values=(index, group["sha256"][:16],
                    core.format_size(group["size"]), path))
        self.summary.configure(text=f"Duplicates: {len(groups)} groups  •  {core.format_size(extra)} potentially redundant storage (no changes made)")
        self.log(f"DUPLICATES: {len(groups)} SHA-256 match groups found; no files deleted.")

    def on_close(self):
        if self.close_requested:
            return
        if self.busy and self.cancel_event:
            if not messagebox.askyesno("Operation Running", "Cancel the operation and close once file work and undo history have finished?"):
                return
            self.close_requested = True
            self.cancel_job()
            self.progress_text.configure(text="Closing after the current operation stops safely…")
            return
        self.finish_close()

    def finish_close(self):
        self.save_settings()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    FileOrganiser(root)
    root.mainloop()
