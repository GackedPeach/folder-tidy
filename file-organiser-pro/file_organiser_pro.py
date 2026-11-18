"""File Organiser Pro v1.0 — original Tkinter prototype, formatting restored."""
import os
import json
import fnmatch
import shutil
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

APP_NAME = "File Organiser Pro"
CONFIG_FILE = Path.home() / ".file_organiser_pro.json"
DEFAULT_CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif", ".ico", ".heic", ".raw"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpeg", ".mpg", ".m4v", ".3gp"],
    "Audio": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".aiff", ".opus"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md", ".epub"],
    "Spreadsheets": [".xls", ".xlsx", ".csv", ".ods", ".tsv"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
    "Programs": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".apk", ".appimage", ".bat", ".sh"],
    "Code": [".py", ".java", ".cpp", ".c", ".h", ".html", ".css", ".js", ".ts", ".json", ".php", ".sql", ".xml", ".yml", ".yaml", ".go", ".rs", ".swift", ".ipynb"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
    "3D Files": [".blend", ".obj", ".fbx", ".stl", ".gltf", ".glb", ".dae"],
    "Design": [".psd", ".ai", ".eps", ".indd", ".xcf", ".fig", ".sketch"],
    "Database": [".db", ".sqlite", ".sqlite3", ".mdb"]
}
DEFAULT_SETTINGS = {
    "recursive": False,
    "skip_hidden": True,
    "output_folder": "Organised",
    "ignore_patterns": [".tmp", ".temp", ".part", ".crdownload", "desktop.ini", "Thumbs.db", ".DS_Store"],
    "custom_categories": {},
    "ignored_extensions": [],
    "organisation_mode": "Category"
}
MODES = ["Category", "Extension", "Date Modified", "Date Created", "File Size"]


class FileOrganiser:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1050x760")
        self.root.minsize(800, 600)
        self.settings = self.load_settings()
        self.folder_path = tk.StringVar()
        self.recursive = tk.BooleanVar(value=self.settings["recursive"])
        self.skip_hidden = tk.BooleanVar(value=self.settings["skip_hidden"])
        self.mode = tk.StringVar(value=self.settings["organisation_mode"])
        self.output_folder = tk.StringVar(value=self.settings["output_folder"])
        self.ignore_text = tk.StringVar(value=", ".join(self.settings["ignore_patterns"]))
        self.ignore_extensions = tk.StringVar(value=", ".join(self.settings["ignored_extensions"]))
        self.planned_moves = []
        self.last_moves = []
        self.scanned_files = []
        self.busy = False
        self.setup_style()
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_settings(self):
        settings = DEFAULT_SETTINGS.copy()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    settings.update(json.load(f))
            except (OSError, json.JSONDecodeError):
                pass
        return settings

    def save_settings(self):
        self.settings.update({
            "recursive": self.recursive.get(),
            "skip_hidden": self.skip_hidden.get(),
            "output_folder": self.output_folder.get(),
            "ignore_patterns": self.parse_list(self.ignore_text.get()),
            "ignored_extensions": [
                x.lower() if x.startswith(".") else "." + x.lower()
                for x in self.parse_list(self.ignore_extensions.get())
            ],
            "organisation_mode": self.mode.get()
        })
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except OSError as e:
            self.log(f"Could not save settings: {e}")

    @staticmethod
    def parse_list(value):
        return [x.strip() for x in value.split(",") if x.strip()]

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def setup_ui(self):
        header = ttk.Frame(self.root, padding=(20, 15))
        header.pack(fill="x")
        ttk.Label(header, text="FILE ORGANISER PRO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="A smarter way to organise, manage and clean your files.", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        folder_frame = ttk.LabelFrame(self.root, text=" Folder Selection ", padding=12)
        folder_frame.pack(fill="x", padx=20, pady=5)
        ttk.Entry(folder_frame, textvariable=self.folder_path).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).pack(side="right")
        settings = ttk.LabelFrame(self.root, text=" Organisation Settings ", padding=12)
        settings.pack(fill="x", padx=20, pady=6)
        row1 = ttk.Frame(settings)
        row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="Organisation method:").pack(side="left")
        ttk.Combobox(row1, textvariable=self.mode, values=MODES, state="readonly", width=19).pack(side="left", padx=8)
        ttk.Label(row1, text="Output folder:").pack(side="left", padx=(20, 5))
        ttk.Entry(row1, textvariable=self.output_folder, width=22).pack(side="left")
        row2 = ttk.Frame(settings)
        row2.pack(fill="x", pady=5)
        ttk.Checkbutton(row2, text="Include subfolders", variable=self.recursive).pack(side="left", padx=(0, 20))
        ttk.Checkbutton(row2, text="Skip hidden files", variable=self.skip_hidden).pack(side="left")
        filters = ttk.LabelFrame(self.root, text=" Filters and Exclusions ", padding=12)
        filters.pack(fill="x", padx=20, pady=5)
        ttk.Label(filters, text="Ignore filenames / patterns (comma separated):").pack(anchor="w")
        ttk.Entry(filters, textvariable=self.ignore_text).pack(fill="x", pady=(3, 8))
        ttk.Label(filters, text="Ignore extensions (comma separated, e.g. .tmp, .log):").pack(anchor="w")
        ttk.Entry(filters, textvariable=self.ignore_extensions).pack(fill="x", pady=(3, 3))
        buttons = ttk.Frame(self.root)
        buttons.pack(pady=12)
        for label, command in [
            ("Scan Files", self.scan_folder),
            ("Preview", self.preview_moves),
            ("Organise", self.organise_files),
            ("Undo Last", self.undo_last),
            ("Custom Categories", self.edit_categories),
            ("Open Folder", self.open_folder)
        ]:
            ttk.Button(buttons, text=label, command=command, style="Action.TButton").pack(side="left", padx=4)
        self.summary = ttk.Label(self.root, text="Select a folder to get started.", font=("Segoe UI", 10, "bold"))
        self.summary.pack(pady=5)
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=25, pady=5)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        preview_tab = ttk.Frame(notebook, padding=8)
        notebook.add(preview_tab, text="File Preview")
        columns = ("name", "category", "destination", "size")
        self.tree = ttk.Treeview(preview_tab, columns=columns, show="headings")
        headings = {"name": "File Name", "category": "Category", "destination": "Destination", "size": "Size"}
        widths = {"name": 230, "category": 130, "destination": 330, "size": 90}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col])
        scrollbar = ttk.Scrollbar(preview_tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        log_tab = ttk.Frame(notebook, padding=8)
        notebook.add(log_tab, text="Activity Log")
        self.log_box = tk.Text(log_tab, font=("Consolas", 9), wrap="word", state="disabled", bg="#202124", fg="#e8eaed", insertbackground="white")
        log_scroll = ttk.Scrollbar(log_tab, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        ttk.Button(log_tab, text="Clear Log", command=self.clear_log).pack(anchor="e", pady=5)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.save_settings()
            self.log(f"Selected folder: {folder}")
            self.scan_folder()

    def valid_folder(self):
        folder = Path(self.folder_path.get()).expanduser()
        if not folder.is_dir():
            messagebox.showerror("Invalid Folder", "Please select an existing folder.")
            return None
        return folder.resolve()

    def open_folder(self):
        folder = self.valid_folder()
        if not folder:
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(folder))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except (OSError, AttributeError) as e:
            messagebox.showerror("Error", str(e))

    def get_categories(self):
        categories = {key: list(value) for key, value in DEFAULT_CATEGORIES.items()}
        for key, extensions in self.settings.get("custom_categories", {}).items():
            categories[key] = extensions
        return categories

    def edit_categories(self):
        window = tk.Toplevel(self.root)
        window.title("Custom Categories")
        window.geometry("540x420")
        window.transient(self.root)
        ttk.Label(window, text="Create your own file categories", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))
        ttk.Label(window, text="One category per line: Category: .ext, .ext").pack(pady=5)
        editor = tk.Text(window, height=13, font=("Consolas", 10))
        editor.pack(fill="both", expand=True, padx=15, pady=8)
        for category, extensions in self.settings.get("custom_categories", {}).items():
            editor.insert("end", f"{category}: {', '.join(extensions)}\n")

        def save():
            custom = {}
            for line in editor.get("1.0", "end").splitlines():
                if not line.strip():
                    continue
                if ":" not in line:
                    messagebox.showerror("Invalid Format", f"Invalid category line:\n{line}")
                    return
                name, extensions = line.split(":", 1)
                name = name.strip()
                if not name or name in (".", ".."):
                    messagebox.showerror("Invalid Category", "Please enter a valid category name.")
                    return
                if any(c in name for c in r'/:?"<>|'):
                    messagebox.showerror("Invalid Category", "Category names cannot contain filesystem-reserved characters.")
                    return
                custom[name] = [
                    ext.strip().lower() if ext.strip().startswith(".") else "." + ext.strip().lower()
                    for ext in extensions.split(",") if ext.strip()
                ]
            self.settings["custom_categories"] = custom
            self.save_settings()
            self.planned_moves.clear()
            self.log("Custom categories updated.")
            window.destroy()

        ttk.Button(window, text="Save Categories", command=save).pack(pady=12)

    def get_category(self, file):
        ext = file.suffix.lower()
        for category, extensions in self.get_categories().items():
            if ext in extensions:
                return category
        return "Others"

    def is_ignored(self, file, root):
        name = file.name
        if self.skip_hidden.get() and name.startswith("."):
            return True
        if name.startswith("~$"):
            return True
        if file.suffix.lower() in self.settings["ignored_extensions"]:
            return True
        patterns = self.parse_list(self.ignore_text.get())
        relative = file.relative_to(root).as_posix()
        for pattern in patterns:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                return True
            if fnmatch.fnmatch(relative.lower(), pattern.lower()):
                return True
        return False

    def get_files(self):
        root = self.valid_folder()
        if not root:
            return []
        output_name = self.output_folder.get().strip()
        if not output_name or output_name in (".", ".."):
            messagebox.showerror("Invalid Output", "Please enter a valid output folder name.")
            return []
        if Path(output_name).is_absolute() or len(Path(output_name).parts) != 1:
            messagebox.showerror("Invalid Output", "The output folder must be a single folder name.")
            return []
        output = root / output_name
        if output.resolve() == root:
            messagebox.showerror("Invalid Output", "The output folder cannot be the selected folder.")
            return []
        files = []
        errors = 0

        def walk_error(error):
            nonlocal errors
            errors += 1
            self.log(f"SCAN ERROR: {error}")

        if self.recursive.get():
            for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
                current_path = Path(current)
                dirs[:] = [
                    d for d in dirs
                    if not (current_path == root and d == output_name)
                    and not (Path(current) / d).is_symlink()
                ]
                for name in filenames:
                    file = current_path / name
                    try:
                        if not file.is_file() or file.is_symlink():
                            continue
                        if not self.is_ignored(file, root):
                            files.append(file)
                    except OSError as e:
                        errors += 1
                        self.log(f"SKIPPED {name}: {e}")
        else:
            try:
                for file in root.iterdir():
                    if not file.is_file() or file.is_symlink():
                        continue
                    if not self.is_ignored(file, root):
                        files.append(file)
            except OSError as e:
                self.log(f"SCAN ERROR: {e}")
        self.log(f"Scan completed: {len(files)} files, {errors} errors.")
        return sorted(files, key=lambda f: str(f).lower())

    @staticmethod
    def format_size(size):
        value = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024

    def get_destination_category(self, file):
        mode = self.mode.get()
        if mode == "Category":
            return self.get_category(file)
        if mode == "Extension":
            return file.suffix.lower().replace(".", "").upper() or "No Extension"
        if mode in ("Date Modified", "Date Created"):
            stat = file.stat()
            if mode == "Date Modified":
                timestamp = stat.st_mtime
            else:
                timestamp = getattr(stat, "st_birthtime", stat.st_ctime)
            date = datetime.fromtimestamp(timestamp)
            return str(date.year) + "/" + date.strftime("%m - %B")
        if mode == "File Size":
            size = file.stat().st_size
            if size < 1024 * 1024:
                return "Small - Under 1 MB"
            if size < 100 * 1024 * 1024:
                return "Medium - 1 to 100 MB"
            if size < 1024 * 1024 * 1024:
                return "Large - 100 MB to 1 GB"
            return "Huge - Over 1 GB"
        return "Others"

    def make_plan(self):
        root = self.valid_folder()
        if not root:
            return []
        files = self.get_files()
        output = root / self.output_folder.get().strip()
        plan = []
        reserved = set()
        for source in files:
            try:
                category = self.get_destination_category(source)
                destination_folder = output / category
                destination = destination_folder / source.name
                counter = 1
                while destination.exists() or destination in reserved:
                    destination = destination_folder / f"{source.stem}_{counter}{source.suffix}"
                    counter += 1
                reserved.add(destination)
                plan.append({
                    "source": source,
                    "destination": destination,
                    "category": category,
                    "size": source.stat().st_size
                })
            except (OSError, ValueError) as e:
                self.log(f"PREVIEW ERROR {source.name}: {e}")
        return plan

    def preview_moves(self):
        if self.busy:
            return
        self.save_settings()
        self.planned_moves = self.make_plan()
        for item in self.tree.get_children():
            self.tree.delete(item)
        categories = {}
        for move in self.planned_moves:
            source = move["source"]
            destination = move["destination"]
            category = move["category"]
            categories[category] = categories.get(category, 0) + 1
            self.tree.insert("", "end", values=(source.name, category, str(destination), self.format_size(move["size"])))
        total_size = sum(x["size"] for x in self.planned_moves)
        self.summary.config(text=f"{len(self.planned_moves)} files | {len(categories)} groups | {self.format_size(total_size)} total")
        self.log(f"Preview generated: {len(self.planned_moves)} moves.")
        for category, count in sorted(categories.items()):
            self.log(f" {category}: {count} files")

    def organise_files(self):
        if self.busy:
            return
        if not self.planned_moves:
            self.preview_moves()
        if not self.planned_moves:
            return
        if not messagebox.askyesno(
            "Confirm Organisation",
            f"Move {len(self.planned_moves)} files?\n"
            "Files will be moved into your selected output folder.\n"
            "You can use Undo Last to reverse successful moves."
        ):
            return
        valid_plan = []
        for move in self.planned_moves:
            if not move["source"].is_file():
                self.log(f"SKIPPED: Source no longer exists: {move['source']}")
                continue
            if move["destination"].exists():
                self.log(f"SKIPPED: Destination already exists: {move['destination']}")
                continue
            valid_plan.append(move)
        if not valid_plan:
            messagebox.showwarning("Nothing to organise", "No valid moves remain. Please create a new preview.")
            self.planned_moves = []
            return
        self.busy = True
        self.progress["maximum"] = len(valid_plan)
        self.progress["value"] = 0
        moved = 0
        errors = 0
        completed = []
        self.log("========== ORGANISING ==========")
        try:
            for index, move in enumerate(valid_plan, start=1):
                source = move["source"]
                destination = move["destination"]
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        raise FileExistsError("Destination appeared during organisation.")
                    shutil.move(str(source), str(destination))
                    completed.append({"source": source, "destination": destination})
                    moved += 1
                    self.log(f"MOVED: {source.name} -> {move['category']}")
                except (OSError, shutil.Error) as e:
                    errors += 1
                    self.log(f"ERROR: {source.name}: {e}")
                self.progress["value"] = index
                self.summary.config(text=f"Organising... {index}/{len(valid_plan)}")
                self.root.update_idletasks()
        finally:
            self.busy = False
        self.last_moves = completed
        self.planned_moves = []
        self.summary.config(text=f"Complete: {moved} moved | {errors} errors")
        self.log("========== COMPLETE ==========")
        messagebox.showinfo("Organisation Complete", f"Successfully moved: {moved}\nErrors: {errors}\nUse Undo Last to reverse successful moves.")

    def undo_last(self):
        if self.busy:
            return
        if not self.last_moves:
            messagebox.showinfo("Undo", "There are no successful moves to undo.")
            return
        if not messagebox.askyesno("Undo Organisation", f"Reverse the last {len(self.last_moves)} successful moves?"):
            return
        restored = 0
        errors = 0
        remaining = []
        for move in reversed(self.last_moves):
            source = move["source"]
            destination = move["destination"]
            try:
                if not destination.exists():
                    raise FileNotFoundError("Moved file can no longer be found.")
                if source.exists():
                    raise FileExistsError("Original location is already occupied.")
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
                restored += 1
                self.log(f"RESTORED: {source.name}")
            except (OSError, shutil.Error) as e:
                errors += 1
                remaining.append(move)
                self.log(f"UNDO ERROR: {source.name}: {e}")
        self.last_moves = list(reversed(remaining))
        self.summary.config(text=f"Undo complete: {restored} restored | {errors} errors")
        messagebox.showinfo("Undo Complete", f"Restored: {restored}\nErrors: {errors}")

    def scan_folder(self):
        if self.busy:
            return
        self.save_settings()
        files = self.get_files()
        self.scanned_files = files
        if not files:
            self.summary.config(text="No matching files found.")
            return
        categories = {}
        total_size = 0
        for file in files:
            try:
                category = self.get_destination_category(file)
                categories[category] = categories.get(category, 0) + 1
                total_size += file.stat().st_size
            except OSError as e:
                self.log(f"SCAN ERROR: {file.name}: {e}")
        self.summary.config(text=f"{len(files)} files | {len(categories)} groups | {self.format_size(total_size)} total")
        self.planned_moves = []
        self.log("========== SCAN RESULTS ==========")
        for category, count in sorted(categories.items()):
            self.log(f"{category}: {count} files")
        self.log(f"Total size: {self.format_size(total_size)}")

    def on_close(self):
        self.save_settings()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = FileOrganiser(root)
    root.mainloop()
