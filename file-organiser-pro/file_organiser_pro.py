"""File Organiser Pro 1.2 — copy-only Tkinter desktop interface.

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
        root.geometry("1180x820")
        root.minsize(1020, 720)
        self.settings = core.load_settings()

        self.folder_path = tk.StringVar(value=str(self.settings.get("last_folder", "")))
        self.recursive = tk.BooleanVar(value=self.settings["recursive"])
        self.skip_hidden = tk.BooleanVar(value=self.settings["skip_hidden"])
        self.mode = tk.StringVar(value=core.MODE_LABELS[self.settings["organisation_mode"]])
        self.date_group = tk.StringVar(value=self.settings["date_granularity"])
        self.output_folder = tk.StringVar(value=self.settings["output_folder"])
        self.ignore_text = tk.StringVar(value=", ".join(self.settings["ignore_patterns"]))
        self.ignore_extensions = tk.StringVar(value=", ".join(self.settings["ignored_extensions"]))
        self.exclude_dirs = tk.StringVar(value=", ".join(self.settings["excluded_directories"]))
        self.include_extensions = tk.StringVar(value=", ".join(self.settings["include_extensions"]))
        self.filename_pattern = tk.StringVar(value=str(self.settings["filename_pattern"]))
        self.min_size = tk.StringVar(value=str(self.settings["min_size"]))
        self.max_size = tk.StringVar(value=str(self.settings["max_size"]))
        self.theme_var = tk.StringVar(value=self.settings["theme"])

        self.planned_copies: list[dict] = []
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
        self.update_actions()

    def bind_changes(self):
        relevant = [self.folder_path, self.recursive, self.skip_hidden, self.mode,
                    self.output_folder, self.ignore_text, self.ignore_extensions,
                    self.exclude_dirs, self.include_extensions, self.filename_pattern,
                    self.min_size, self.max_size, self.date_group]
        for var in relevant:
            var.trace_add("write", self.invalidate_plan)
        self.theme_var.trace_add("write", lambda *_: self.apply_theme())
        for var in (self.mode, self.folder_path, self.output_folder, self.date_group):
            var.trace_add("write", self.update_sort_hint)
        self.update_sort_hint()

    def settings_snapshot(self) -> dict:
        value = copy.deepcopy(self.settings)
        value.update({
            "recursive": self.recursive.get(), "skip_hidden": self.skip_hidden.get(),
            "organisation_mode": {v: k for k, v in core.MODE_LABELS.items()}.get(self.mode.get(), self.mode.get()),
            "date_granularity": self.date_group.get(), "output_folder": self.output_folder.get(),
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
        header = ttk.Frame(self.root, padding=(24, 20, 24, 16))
        header.pack(fill="x")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="File Organiser Pro", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="A clearer home for your files.", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(header, text=" ORIGINALS KEPT ", style="Safe.TLabel", padding=(10, 6)).pack(side="right", padx=(14, 0))
        theme = ttk.Combobox(header, textvariable=self.theme_var, values=["Dark", "Light"], state="readonly", width=7)
        theme.pack(side="right", padx=(10, 0))
        self.editable_widgets.append((theme, "readonly"))
        ttk.Label(header, text=f"v{core.APP_VERSION}", style="Sub.TLabel").pack(side="right", padx=12)

        body = ttk.Frame(self.root, padding=(24, 0, 24, 20))
        body.pack(fill="both", expand=True)
        side_shell = ttk.Frame(body, style="Sidebar.TFrame", width=300)
        side_shell.pack(side="left", fill="y", padx=(0, 20))
        side_shell.pack_propagate(False)
        bottom = ttk.Frame(side_shell, style="Sidebar.TFrame", padding=20)
        bottom.pack(side="bottom", fill="x")
        scroll_area = ttk.Frame(side_shell, style="Sidebar.TFrame")
        scroll_area.pack(fill="both", expand=True)
        self.side_canvas = tk.Canvas(scroll_area, highlightthickness=0, borderwidth=0, width=282)
        side_scroll = ttk.Scrollbar(scroll_area, orient="vertical", command=self.side_canvas.yview)
        self.side_canvas.configure(yscrollcommand=side_scroll.set)
        side_scroll.pack(side="right", fill="y")
        self.side_canvas.pack(side="left", fill="both", expand=True)
        sidebar = ttk.Frame(self.side_canvas, style="Sidebar.TFrame", padding=(20, 20, 12, 10))
        side_window = self.side_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", lambda _: self.side_canvas.configure(scrollregion=self.side_canvas.bbox("all")))
        self.side_canvas.bind("<Configure>", lambda event: self.side_canvas.itemconfigure(side_window, width=event.width))

        def scroll_sidebar(event, units):
            if (self.side_canvas.winfo_rootx() <= event.x_root < self.side_canvas.winfo_rootx() + self.side_canvas.winfo_width()
                    and self.side_canvas.winfo_rooty() <= event.y_root < self.side_canvas.winfo_rooty() + self.side_canvas.winfo_height()):
                self.side_canvas.yview_scroll(units, "units")

        self.root.bind("<MouseWheel>", lambda e: scroll_sidebar(e, -int(e.delta / 120)), add="+")
        self.root.bind("<Button-4>", lambda e: scroll_sidebar(e, -1), add="+")
        self.root.bind("<Button-5>", lambda e: scroll_sidebar(e, 1), add="+")
        ttk.Label(sidebar, text="01  Choose your files", style="SideHeading.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(sidebar, text="Source folder", style="SideSub.TLabel").pack(anchor="w")
        entry = ttk.Entry(sidebar, textvariable=self.folder_path)
        entry.pack(fill="x", pady=(6, 8))
        self.editable_widgets.append((entry, "normal"))
        choose = ttk.Frame(sidebar, style="Sidebar.TFrame")
        choose.pack(fill="x")
        self.add_button(choose, "Browse…", self.browse_folder)
        self.add_button(choose, "Open source", self.open_folder)
        check = ttk.Checkbutton(sidebar, text="Include subfolders", variable=self.recursive, style="Side.TCheckbutton")
        check.pack(anchor="w", pady=(12, 20))
        self.editable_widgets.append((check, "normal"))
        ttk.Label(sidebar, text="02  Choose a layout", style="SideHeading.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(sidebar, text="Organise by", style="SideSub.TLabel").pack(anchor="w")
        method = ttk.Combobox(sidebar, textvariable=self.mode, values=list(core.MODE_LABELS.values()), state="readonly")
        method.pack(fill="x", pady=(6, 10))
        self.editable_widgets.append((method, "readonly"))
        self.date_label = ttk.Label(sidebar, text="Date grouping", style="SideSub.TLabel")
        self.date_label.pack(anchor="w", pady=(0, 6))
        self.date_combo = ttk.Combobox(sidebar, textvariable=self.date_group, values=core.DATE_GROUPS, state="readonly")
        self.date_combo.pack(fill="x", pady=(0, 8))
        self.editable_widgets.append((self.date_combo, "readonly"))
        self.sort_hint = ttk.Label(sidebar, text="", wraplength=240, style="SideSub.TLabel", justify="left")
        self.sort_hint.pack(anchor="w", fill="x", pady=(0, 18))
        ttk.Label(sidebar, text="Results folder name", style="SideSub.TLabel").pack(anchor="w")
        out_entry = ttk.Entry(sidebar, textvariable=self.output_folder)
        out_entry.pack(fill="x", pady=(6, 6))
        self.editable_widgets.append((out_entry, "normal"))
        ttk.Label(sidebar, text="Created inside your source folder. Originals stay where they are.",
                  style="SideSub.TLabel", wraplength=240).pack(anchor="w", fill="x")
        advanced = self.add_button(sidebar, "Advanced options…", self.open_filters)
        advanced.pack_configure(side="top", anchor="w", pady=(16, 0))
        ttk.Label(sidebar, text="Filters apply. Review Advanced options to choose which files to include.",
                  style="SideSub.TLabel", wraplength=240).pack(anchor="w", pady=(8, 0))
        preview = self.add_button(bottom, "1. Preview files", self.preview_copies)
        preview.pack_configure(side="top", fill="x", pady=(0, 8))
        self.copy_btn = self.add_button(bottom, "2. Organise copies", self.organise_files, style="Primary.TButton")
        self.copy_btn.pack_configure(side="top", fill="x")

        workspace = ttk.Frame(body)
        workspace.pack(side="left", fill="both", expand=True)
        heading = ttk.Frame(workspace)
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="Your organised copies", style="Heading.TLabel").pack(side="left")
        self.add_button(heading, "Open results", self.open_results, side="right")
        self.summary = ttk.Label(workspace, text="Choose a folder, then preview your organised copies.",
                                 style="Summary.TLabel", wraplength=750)
        self.summary.pack(anchor="w", fill="x", pady=(0, 10))
        self.notebook = ttk.Notebook(workspace)
        self.notebook.pack(fill="both", expand=True)
        preview_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(preview_tab, text="Copy preview")
        selection_bar = ttk.Frame(preview_tab)
        selection_bar.pack(fill="x", pady=(0, 10))
        for label, cmd in [("Include all", lambda: self.select_all(True)),
                           ("Exclude all", lambda: self.select_all(False)),
                           ("Toggle selected", self.toggle_highlighted)]:
            ttk.Button(selection_bar, text=label, command=cmd).pack(side="left", padx=(0, 6))
        self.tree = self.make_tree(preview_tab,
            ("include", "name", "category", "destination", "size"),
            ("Include", "Original file", "Group", "Copy destination", "Size"),
            (58, 210, 125, 270, 85))
        self.tree.bind("<Double-1>", self.on_preview_double_click)
        self.tree.bind("<space>", lambda _: self.toggle_highlighted())
        ttk.Label(preview_tab, text="Double-click a row or press Space to include or exclude it.",
                  style="Sub.TLabel").pack(anchor="w", pady=(10, 0))

        duplicate_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(duplicate_tab, text="Duplicates")
        dup_top = ttk.Frame(duplicate_tab)
        dup_top.pack(fill="x", pady=(0, 10))
        self.add_button(dup_top, "Find duplicate files", self.find_duplicates)
        ttk.Label(duplicate_tab, text="Files with identical contents. Review only; nothing is removed.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 10))
        self.duplicates_tree = self.make_tree(duplicate_tab,
            ("group", "hash", "size", "path"), ("Group", "Content ID", "Size", "Original file"),
            (60, 130, 85, 470))
        log_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(log_tab, text="Activity")
        log_buttons = ttk.Frame(log_tab)
        log_buttons.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(log_buttons, text="Export activity…", command=self.export_log).pack(side="left")
        self.report_btn = ttk.Button(log_buttons, text="Open last report", command=self.open_last_report)
        self.report_btn.pack(side="left", padx=6)
        ttk.Button(log_buttons, text="Clear view", command=self.clear_log).pack(side="right")
        text_frame = ttk.Frame(log_tab)
        text_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(text_frame, font=("Consolas", 10), wrap="word", state="disabled",
                               borderwidth=0, highlightthickness=0, padx=10, pady=10)
        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        status = ttk.Frame(workspace, padding=(0, 14, 0, 0))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 8))
        self.cancel_btn = ttk.Button(status, text="Cancel", command=self.cancel_job, state="disabled")
        self.cancel_btn.pack(side="right", padx=(10, 0))
        self.progress_text = ttk.Label(status, text="Ready · Originals stay in place", style="Sub.TLabel", wraplength=600)
        self.progress_text.pack(side="left", fill="x", expand=True)

    def update_sort_hint(self, *_):
        mode = {v: k for k, v in core.MODE_LABELS.items()}.get(self.mode.get(), self.mode.get())
        date_mode = mode in ("Date Modified", "Date Created")
        self.date_combo.configure(state="readonly" if date_mode and not self.busy else "disabled")
        if date_mode:
            self.date_label.pack(before=self.sort_hint, anchor="w", pady=(0, 6))
            self.date_combo.pack(before=self.sort_hint, fill="x", pady=(0, 8))
        else:
            self.date_label.pack_forget()
            self.date_combo.pack_forget()
        hints = {"Category": "Images, Videos, Audio, Documents and more.",
                 "Extension": "One folder per extension: MP4, JPG, PDF and more.",
                 "File Size": "Group copies into small, medium, large and huge files.",
                 "Date Modified": "Group by the file’s last modified date. Photo capture dates are not read.",
                 "Date Created": "Group by creation date; use modified date if unavailable. Photo capture dates are not read."}
        hint = hints.get(mode, "Choose how to group your copies.")
        if date_mode:
            hint += f" Grouping: {self.date_group.get().lower()}."
        self.sort_hint.configure(text=hint)

    def open_filters(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced options")
        dialog.geometry("650x530")
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose which files to include", style="Heading.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Checkbutton(body, text="Skip hidden files and folders", variable=self.skip_hidden).pack(anchor="w", pady=(0, 12))
        for label, var in [("Ignore names or patterns", self.ignore_text),
                           ("Ignore extensions", self.ignore_extensions),
                           ("Exclude folders", self.exclude_dirs),
                           ("Only include extensions", self.include_extensions),
                           ("Filename pattern", self.filename_pattern)]:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=23).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        sizes = ttk.Frame(body)
        sizes.pack(fill="x", pady=(12, 8))
        self.filter_field(sizes, "Min size", self.min_size, width=10)
        self.filter_field(sizes, "Max size", self.max_size, width=10)
        ttk.Label(body, text="Separate lists with commas. Examples: .mp4, .jpg · *.pdf · 100 KB · 2 GB",
                  style="Sub.TLabel", wraplength=590).pack(anchor="w", pady=8)
        ttk.Button(body, text="Custom file types…", command=lambda: self.edit_categories(dialog)).pack(anchor="w", pady=8)

        def done():
            try:
                core.validate_filters(self.settings_snapshot())
                self.save_settings()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("Check your filters", str(exc), parent=dialog)

        ttk.Button(body, text="Done", command=done, style="Primary.TButton").pack(side="bottom", anchor="e")

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
        bg, fg = ("#101722", "#e6edf7") if dark else ("#f3f5f9", "#1d2939")
        panel, field = ("#1a2433", "#111c2b") if dark else ("#ffffff", "#ffffff")
        muted = "#9cacc1" if dark else "#526176"
        border = "#2b3a4e" if dark else "#d4dce6"
        font = "Segoe UI" if platform.system() == "Windows" else "Helvetica"
        self.root.configure(background=bg)
        s = self.style
        s.configure(".", font=(font, 10), background=bg, foreground=fg,
                    bordercolor=border, lightcolor=border, darkcolor=border, focuscolor=border)
        s.configure("TFrame", background=bg)
        s.configure("Sidebar.TFrame", background=panel)
        s.configure("TLabel", background=bg, foreground=fg)
        s.configure("Title.TLabel", font=(font, 22, "bold"))
        s.configure("Heading.TLabel", font=(font, 14, "bold"))
        s.configure("Summary.TLabel", foreground=muted, font=(font, 10))
        s.configure("Sub.TLabel", foreground=muted)
        s.configure("SideHeading.TLabel", background=panel, font=(font, 11, "bold"))
        s.configure("SideSub.TLabel", background=panel, foreground=muted, font=(font, 9))
        s.configure("Safe.TLabel", background="#193e33" if dark else "#dcf4e6",
                    foreground="#8de3b2" if dark else "#17643a", font=(font, 9, "bold"))
        s.configure("TButton", background=panel, foreground=fg, padding=(10, 7), borderwidth=1,
                    bordercolor=border, focuscolor=border)
        s.map("TButton", background=[("active", "#2c405b" if dark else "#e7eef8")],
              foreground=[("disabled", "#67758a")])
        s.configure("Primary.TButton", background="#2f6fec", foreground="white", borderwidth=0,
                    padding=(12, 10), font=(font, 10, "bold"))
        s.map("Primary.TButton", background=[("disabled", "#33435b" if dark else "#d5dfef"),
                    ("active", "#255ccb")], foreground=[("disabled", "#8c9aaf"), ("!disabled", "white")])
        s.configure("TCheckbutton", background=bg, foreground=fg)
        s.configure("Side.TCheckbutton", background=panel, foreground=fg)
        s.map("Side.TCheckbutton", background=[("active", panel)])
        s.map("TCheckbutton", background=[("active", bg)])
        s.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg, padding=7,
                    bordercolor=border, lightcolor=border, darkcolor=border)
        s.configure("TCombobox", fieldbackground=field, foreground=fg, background=panel,
                    arrowcolor=fg, padding=6, bordercolor=border)
        s.map("TCombobox", fieldbackground=[("readonly", field), ("disabled", panel)],
              foreground=[("disabled", muted), ("readonly", fg)])
        s.configure("Treeview", fieldbackground=field, background=field, foreground=fg,
                    rowheight=32, bordercolor=border, borderwidth=0)
        s.configure("Treeview.Heading", background=panel, foreground=muted, padding=(8, 10),
                    font=(font, 9, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", "#224c80" if dark else "#d8e8fc")],
              foreground=[("selected", "#ffffff" if dark else "#15375a")])
        s.configure("TNotebook", background=bg, borderwidth=0, bordercolor=border)
        s.configure("TNotebook.Tab", background=bg, foreground=muted, padding=(16, 10))
        s.map("TNotebook.Tab", background=[("selected", panel)], foreground=[("selected", fg)])
        s.configure("Horizontal.TProgressbar", background="#2f6fec", troughcolor=panel,
                    borderwidth=0, thickness=6)
        s.configure("TScrollbar", background=panel, troughcolor=field, arrowcolor=muted,
                    borderwidth=0, arrowsize=12)
        self.side_canvas.configure(background=panel)
        self.log_box.configure(bg=field, fg=fg, insertbackground=fg)
        self.tree.tag_configure("excluded", foreground="#73839a" if dark else "#8390a1")

    def invalidate_plan(self, *_):
        self.render_generation += 1
        self.preview_context = None
        if not self.planned_copies:
            self.update_actions()
            return
        self.planned_copies = []
        self.clear_tree(self.tree)
        self.update_actions()
        if not self.busy:
            self.summary.configure(text="Settings changed. Generate a new preview before organising.")
            self.progress_text.configure(text="Preview needed")

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
            with open(filename, "x", encoding="utf-8", newline="") as f:
                if Path(filename).suffix.lower() == ".csv":
                    writer = csv.DictWriter(f, fieldnames=["timestamp", "status", "message"])
                    writer.writeheader()
                    writer.writerows(self.log_entries)
                else:
                    for item in self.log_entries:
                        f.write(f"[{item['timestamp']}] {item['message']}\n")
            self.log(f"EXPORTED: {filename}")
        except OSError as exc:
            messagebox.showerror("Export Failed", "Choose a new filename; existing files are kept.\n\n" + str(exc))

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

    def edit_categories(self, parent=None):
        if self.busy:
            return
        owner = parent or self.root
        dialog = tk.Toplevel(owner)
        dialog.title("Custom Categories")
        dialog.geometry("540x430")
        dialog.transient(owner)
        dialog.grab_set()
        def close():
            dialog.destroy()
            if parent is not None and parent.winfo_exists():
                parent.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", close)
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
                close()
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
            self.update_actions()

    def update_actions(self):
        if not self.busy:
            chosen = any(p.get("selected", True) for p in self.planned_copies)
            self.copy_btn.configure(state="normal" if chosen and self.preview_context else "disabled")
        self.report_btn.configure(state="normal" if core.load_history().get("report") else "disabled")
        self.update_sort_hint()

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
        if isinstance(result, dict) and (result.get("report_error") or result.get("history_error")):
            messagebox.showwarning("Copy report needs attention",
                "Your originals remain in place. A report or session summary could not be fully saved.\n\n"
                "Review Activity and export it before closing.")
            self.close_requested = False
        if self.close_requested:
            return
        if name == "scan":
            self.scanned_files = result
            self.invalidate_plan()
            size = sum(item["snapshot"]["size"] for item in result)
            self.summary.configure(text=f"{len(result)} matching files · {core.format_size(size)} to copy")
        elif name == "preview":
            self.scanned_files, self.planned_copies = result
            self.preview_context = self.pending_preview_context
            self.notebook.select(0)
            self.populate_preview()
        elif name == "duplicates":
            self.populate_duplicates(result)
        elif name == "organise":
            self.invalidate_plan()
            self.scanned_files = []
            state = "Stopped" if result["cancelled"] or result.get("report_error") else "Finished"
            self.summary.configure(text=f"{state}: {result['copied']} copied · {result['skipped']} skipped · {result['errors']} errors")
            self.log(f"RESULT: {self.summary.cget('text')}. Originals kept in place.")
            self.update_actions()
        if isinstance(result, dict) and (result.get("report_error") or result.get("history_error")):
            self.progress_text.configure(text="Report needs attention. Your originals are unchanged.")
        elif name != "preview":
            self.progress_text.configure(text="Stopped safely · Originals kept" if isinstance(result, dict) and result.get("cancelled")
                                         else "Finished · Originals kept")

    def scan_folder(self):
        try:
            root, settings = self.validate_input()
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return
        self.start_job("scan", lambda p, l, c: core.scan(root, settings, p, l, c))

    def preview_copies(self):
        try:
            root, settings = self.validate_input()
            self.save_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return

        def run(progress, logger, cancel):
            records = core.scan(root, settings, progress, logger, cancel)
            return records, core.build_plan(records, root, settings, logger, cancel)

        self.planned_copies = []
        self.preview_context = None
        self.pending_preview_context = self.plan_context(root, settings)
        self.clear_tree(self.tree)
        self.start_job("preview", run)

    @staticmethod
    def plan_context(root, settings):
        # Appearance does not affect which files are copied or where they go.
        return str(root), {key: copy.deepcopy(value) for key, value in settings.items() if key != "theme"}

    def relative_path(self, path):
        try:
            return str(Path(path).relative_to(Path(self.folder_path.get()).expanduser()))
        except ValueError:
            return str(path)

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
            stop = min(start + 200, len(self.planned_copies))
            for index in range(start, stop):
                item = self.planned_copies[index]
                self.tree.insert("", "end", iid=f"p{index}", values=("✓" if item["selected"] else "–",
                    self.relative_path(item["source"]), item["category"], self.relative_path(item["destination"]), core.format_size(item["size"])),
                    tags=() if item["selected"] else ("excluded",))
            if stop < len(self.planned_copies):
                self.progress_text.configure(text=f"Loading preview: {stop} / {len(self.planned_copies)}")
                self.root.after(1, lambda: insert_batch(stop))
            else:
                self.set_busy(False)
                self.refresh_selection_summary()
                self.progress_text.configure(text="Preview ready")

        insert_batch()

    def refresh_selection_summary(self):
        included = [p for p in self.planned_copies if p["selected"]]
        total_size = sum(p["size"] for p in included)
        self.summary.configure(text=f"{len(included)} of {len(self.planned_copies)} files selected · {core.format_size(total_size)} of additional space")
        self.update_actions()

    def select_all(self, checked):
        if self.busy:
            return
        for item in self.planned_copies:
            item["selected"] = checked
        self.populate_preview()

    def toggle_highlighted(self):
        if self.busy:
            return
        for row in self.tree.selection():
            index = int(row[1:])
            if index < len(self.planned_copies):
                obj = self.planned_copies[index]
                obj["selected"] = not obj["selected"]
                self.tree.item(row, values=("✓" if obj["selected"] else "–", self.relative_path(obj["source"]),
                                   obj["category"], self.relative_path(obj["destination"]), core.format_size(obj["size"])),
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
        if not self.planned_copies:
            messagebox.showinfo("Preview Required", "Preview and select files before creating organised copies.")
            return
        chosen = sum(bool(p["selected"]) for p in self.planned_copies)
        if not chosen:
            messagebox.showinfo("Nothing Selected", "Select at least one file in the preview.")
            return
        # Checking again prevents execution with changed input configuration.
        try:
            root, settings = self.validate_input()
            if self.preview_context != self.plan_context(root, settings):
                raise ValueError("Folder or settings changed; recreate the preview.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return
        output = core.get_output(root, settings)
        notice = (f"Create organised copies of {chosen} selected files?\n\n"
                  f"Results: {output}\n\n"
                  "All originals stay in their current locations.\n"
                  "Each copy is checked after writing. Existing files are never replaced.\n"
                  "A copy report is saved in the results folder.")
        if not messagebox.askyesno("Organise copies", notice):
            return
        plan = copy.deepcopy(self.planned_copies)
        self.start_job("organise", lambda p, l, c: core.organise(plan, root, p, l, c, output=output))

    @staticmethod
    def open_path(path):
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def open_results(self):
        try:
            root, settings = self.validate_input()
            output = core.get_output(root, settings)
            if not output.is_dir():
                messagebox.showinfo("Your results", "Organise copies first to create your results folder.")
                return
            self.open_path(output)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Open results", str(exc))

    def open_last_report(self):
        path = Path(core.load_history().get("report", ""))
        if not path.is_file():
            messagebox.showinfo("Copy report", "No saved report is available yet.")
            return
        try:
            self.open_path(path)
        except OSError as exc:
            messagebox.showerror("Open report", str(exc))

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
            if not messagebox.askyesno("Operation Running", "Cancel the operation and close when the current copy and report have finished?"):
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
