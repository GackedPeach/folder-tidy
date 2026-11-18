## File Organiser Pro 1.2.0-beta.2

Small fix for a frustrating one: opening and closing Advanced options could leave the app stuck when you clicked Preview files. That's fixed, with a regression check in both the GUI tests and packaged app check.

The app now shows the full results-folder path, and scan/preview statuses make it clear that no files have been copied yet. Use **Organise copies** after reviewing the preview to create the output.

Ready-to-run downloads are attached below. **You do not need Python.**

| Your computer | Download |
| --- | --- |
| Windows 10/11, 64-bit | `FileOrganiserPro-v1.2.0-beta.2-windows-x64.exe` |
| Mac with Apple Silicon (M1 or newer), macOS 15+ | `FileOrganiserPro-v1.2.0-beta.2-macos-arm64.dmg` |
| Intel Mac, macOS 15+ | `FileOrganiserPro-v1.2.0-beta.2-macos-x64.dmg` |
| Linux, 64-bit, glibc 2.35+ (Ubuntu 22.04+ and compatible) | `FileOrganiserPro-v1.2.0-beta.2-linux-x64.tar.gz` |

**Windows:** download and open the `.exe`.
**Mac:** open the `.dmg`, drag the app to Applications, then open it.
**Linux:** extract the whole archive, then open `FileOrganiserPro` inside it. Keep the `_internal` folder alongside the executable. A graphical X11/XWayland desktop is required.

These are unsigned community beta builds. Windows/macOS may require manual approval on first launch; the Mac apps are not Apple-notarised. SHA-256 checksums are attached in `SHA256SUMS.txt`.

### The big update

- **Copies only:** organise into **Files Sorted**, keeping every original in place.
- Group by file type, extension, modified date, creation date, or size.
- Date layouts support year, month and day folders. Dates use filesystem timestamps; photo capture metadata and Google Takeout sidecars are not interpreted.
- Preview destinations, include/exclude individual files, and use advanced filters.
- Independent, verified copies with no replacement of existing files.
- Saved reports, safe cancellation, read-only duplicate detection, and a refreshed dark/light interface.

Start with a small sample while beta testing. This is a work in progress, and feedback is welcome.

[Report a bug](https://github.com/GackedPeach/folder-tidy/issues/new?template=bug_report.yml) · [Read the instructions](https://github.com/GackedPeach/folder-tidy/tree/main/file-organiser-pro) · [Browse the source](https://github.com/GackedPeach/folder-tidy)

The automatically generated **Source code** archives are for people who want to inspect or modify the code. For normal use, choose one of the app downloads above.
