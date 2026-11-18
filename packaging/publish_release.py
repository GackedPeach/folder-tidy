"""Publish all tested native packages together as a GitHub beta release."""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "file-organiser-pro"))
from organiser_core import APP_VERSION


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["RELEASE_COMMIT"]
    token = os.environ["GH_TOKEN"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid release repository or commit")
    if "beta" not in APP_VERSION:
        raise ValueError("This workflow only publishes beta versions")
    tag = f"v{APP_VERSION}"
    assets = REPO / "release-assets"
    prefix = f"FileOrganiserPro-{tag}"
    names = [f"{prefix}-windows-x64.exe", f"{prefix}-macos-arm64.dmg",
             f"{prefix}-macos-x64.dmg", f"{prefix}-linux-x64.tar.gz"]
    for name in names:
        if not (assets / name).is_file() or (assets / name).stat().st_size < 100000:
            raise ValueError(f"Native package is missing or unexpectedly small: {name}")
    checksums = {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in names}
    checksum_file = assets / "SHA256SUMS.txt"
    checksum_file.write_text("".join(f"{checksums[name]}  {name}\n" for name in names), encoding="utf-8")
    names.append(checksum_file.name)
    checksums[checksum_file.name] = hashlib.sha256(checksum_file.read_bytes()).hexdigest()

    def request(method, path, data=None, upload=False):
        url = path if upload else f"https://api.github.com/repos/{repository}{path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "FileOrganiserPro-release"}
        if upload:
            headers["Content-Type"] = "application/octet-stream"
        elif data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)

    try:
        release = request("GET", f"/releases/tags/{tag}")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        release = request("POST", "/releases", {
            "tag_name": tag, "target_commitish": commit,
            "name": f"File Organiser Pro {APP_VERSION} — public beta",
            "body": (REPO / "packaging/RELEASE_NOTES.md").read_text(encoding="utf-8"),
            "draft": True, "prerelease": True, "make_latest": "false"})
    if not release["draft"]:
        raise RuntimeError("This version is already published. Bump APP_VERSION for a new beta; published assets are never replaced.")
    if release["target_commitish"] != commit:
        raise RuntimeError("Existing draft targets a different commit; refusing to replace it")
    existing = {asset["name"]: asset for asset in release["assets"]}
    upload_url = release["upload_url"].split("{", 1)[0]
    for name in names:
        if name in existing:
            asset = existing[name]
            if asset.get("digest") != f"sha256:{checksums[name]}":
                raise RuntimeError(f"An existing draft asset differs: {name}")
        else:
            asset = request("POST", upload_url + "?" + urllib.parse.urlencode({"name": name}),
                            (assets / name).read_bytes(), upload=True)
        if asset["size"] != (assets / name).stat().st_size:
            raise RuntimeError(f"Uploaded asset has an unexpected size: {name}")
        if asset.get("digest") and asset["digest"] != f"sha256:{checksums[name]}":
            raise RuntimeError(f"Uploaded asset checksum differs: {name}")
        print(f"Verified upload: {name}")
    published = request("PATCH", f"/releases/{release['id']}",
                        {"draft": False, "prerelease": True, "make_latest": "false"})
    print(f"Published beta: {published['html_url']}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(f"## Beta downloads are ready\n\n[Open release]({published['html_url']})\n\n")
            output.write("\n".join(f"- {name}" for name in names) + "\n")


if __name__ == "__main__":
    main()
