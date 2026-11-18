"""Build and smoke-test a native package on the current operating system."""
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "file-organiser-pro"
sys.path.insert(0, str(APP))
from organiser_core import APP_VERSION


def main():
    system = platform.system()
    architecture = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    label = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[system]
    work = REPO / "build" / f"{label}-{architecture}"
    dist = work / "dist"
    assets = REPO / "release-assets"
    for folder in (work, dist, assets):
        folder.resolve().relative_to(REPO)
        folder.mkdir(parents=True, exist_ok=True)
    name = "File Organiser Pro" if system == "Darwin" else "FileOrganiserPro"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--name", name, "--distpath", str(dist), "--workpath", str(work / "work"),
               "--specpath", str(work), "--paths", str(APP)]
    command += ["--onefile", "--windowed"] if system == "Windows" else ["--onedir"]
    if system == "Darwin":
        command += ["--windowed", "--osx-bundle-identifier", "io.github.gackedpeach.fileorganiserpro",
                    "--target-architecture", "arm64" if architecture == "arm64" else "x86_64"]
    command.append(str(REPO / "packaging/launcher.py"))
    subprocess.run(command, cwd=REPO, check=True)
    if system == "Windows":
        binary = dist / f"{name}.exe"
    elif system == "Darwin":
        binary = dist / f"{name}.app/Contents/MacOS/{name}"
    else:
        binary = dist / name / name
    smoke_result = work / "packaged-smoke.json"
    check_command = [str(binary), "--smoke-test", str(smoke_result)]
    if system == "Linux":
        check_command = ["xvfb-run", "-a"] + check_command
    try:
        subprocess.run(check_command, check=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if smoke_result.is_file():
            print(smoke_result.read_text(encoding="utf-8"), flush=True)
        raise
    result = json.loads(smoke_result.read_text(encoding="utf-8"))
    if result.get("success") is not True:
        raise RuntimeError(f"Packaged smoke check failed: {result}")
    prefix = f"FileOrganiserPro-v{APP_VERSION}-{label}-{architecture}"
    if system == "Windows":
        package = assets / f"{prefix}.exe"
        shutil.copy2(binary, package)
    elif system == "Darwin":
        staging = work / "disk-image"
        staging.mkdir(exist_ok=True)
        shutil.copytree(dist / f"{name}.app", staging / f"{name}.app", dirs_exist_ok=True, symlinks=True)
        applications = staging / "Applications"
        if not os.path.lexists(applications):
            applications.symlink_to("/Applications", target_is_directory=True)
        (staging / "READ ME.txt").write_text((REPO / "packaging/DOWNLOADS.txt").read_text(encoding="utf-8"), encoding="utf-8")
        package = assets / f"{prefix}.dmg"
        subprocess.run(["hdiutil", "create", "-volname", "File Organiser Pro Beta", "-srcfolder",
                        str(staging), "-ov", "-format", "UDZO", str(package)], check=True)
        subprocess.run(["hdiutil", "verify", str(package)], check=True)
    else:
        (dist / name / "READ ME.txt").write_text((REPO / "packaging/DOWNLOADS.txt").read_text(encoding="utf-8"), encoding="utf-8")
        package = assets / f"{prefix}.tar.gz"
        with tarfile.open(package, "w:gz") as archive:
            archive.add(dist / name, arcname=name)
    print(json.dumps({"package": str(package), "bytes": package.stat().st_size, "smoke_test": result}, indent=2))


if __name__ == "__main__":
    main()
