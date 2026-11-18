# Folder Tidy 🧹 — A Little Less File Chaos

A small Python script that sorts loose files into folders like `Images`,
`Documents`, and `Audio`. Useful for tidying a Downloads folder.

It previews changes first. Nothing moves until you add `--apply`.

## Copy-only desktop app

This repo also includes **[File Organiser Pro](file-organiser-pro/)**, a desktop
app built with Python and Tkinter.

**File Organiser Pro v1.2** creates independent copies in a **Files Sorted**
folder and keeps originals in place. Group by file type, extension, modified
date, creation date, or size. Dates can use year, month, or day folders.
It includes previews, filters, duplicate detection, copy verification, and a
saved report. See its [README](file-organiser-pro/README.md) for setup and limits.

The instructions below are for the original Folder Tidy command-line script,
which **moves files**. Use the desktop app above for copy-only organisation.

## Run it

You need Python 3.10 or newer. There are no packages to install.
Download this repository using **Code > Download ZIP**, unzip it, and open
a terminal in the extracted folder.

Preview a folder:

```sh
python tidy.py "path/to/folder"
```

If the preview looks right:

```sh
python tidy.py "path/to/folder" --apply
```

On Windows, you may need `py` instead of `python`. On macOS or Linux,
you may need `python3`.

Example preview:

```text
Would move: holiday.jpg -> Images/holiday.jpg
Would move: receipt.pdf -> Documents/receipt.pdf
2 file(s) to move.
Preview only. Add --apply to move these files.
```

## A few details

- Only files directly inside the chosen folder are checked.
- Hidden dotfiles, symbolic links, and unknown file types are left alone.
- Existing files are never replaced. Name collisions are skipped.
- File extensions are matched without caring about uppercase or lowercase.
- Edit `GROUPS` near the top of `tidy.py` to change the categories.

Try it on a folder of copies first. There is no automatic undo; you can move
files back yourself. Run it when files in the folder are not being downloaded
or edited. Files are copied before their originals are removed, which needs
some free disk space and does not preserve file timestamps or permissions.
If a move fails, the script stops; earlier moves remain completed. A failed
copy leaves the original intact but may leave a partial destination file.

## Tests

```sh
python -m unittest -v
```
