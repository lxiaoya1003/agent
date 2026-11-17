import hashlib
import os
from pathlib import Path

import requests
from github import Github

SOURCE_REPOSITORY = "lxiaoya1003/agent"
GITEE_OWNER = "hashgopeed"
GITEE_REPOSITORY = "agent"


def download_latest_release():
    github_token = os.getenv("GITHUB_TOKEN")
    github = Github(github_token) if github_token else Github()
    release = github.get_repo(SOURCE_REPOSITORY).get_latest_release()
    files = []
    for asset in release.get_assets():
        path = Path(asset.name)
        response = requests.get(asset.browser_download_url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)
        files.append(path)
        print(f"Downloaded {path.name}")
    checksum_file = Path("checksums.txt")
    if checksum_file.exists():
        verify_checksum(checksum_file)
    else:
        print("checksums.txt not found; skipping checksum verification")
    return release, files


def verify_checksum(checksum_file):
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        path = Path(name.strip().lstrip("*"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError(f"checksum mismatch: {path.name}")
        print(f"{path.name}: OK")


def sync_to_gitee(release, files):
    token = os.environ["GITEE_TOKEN"]
    base = f"https://gitee.com/api/v5/repos/{GITEE_OWNER}/{GITEE_REPOSITORY}/releases"
    payload = {
        "access_token": token,
        "tag_name": release.tag_name,
        "name": release.tag_name,
        "body": release.body or "",
        "prerelease": release.prerelease,
        "target_commitish": "main",
    }
    response = requests.post(base, json=payload, timeout=60)
    if response.status_code == 409:
        existing = requests.get(base, params={"access_token": token}, timeout=60)
        existing.raise_for_status()
        matches = [item for item in existing.json() if item.get("tag_name") == release.tag_name]
        if not matches:
            raise RuntimeError(f"Gitee release creation failed: {response.status_code} {response.text}")
        release_id = matches[0]["id"]
        print(f"Gitee release already exists: {release_id}")
    else:
        response.raise_for_status()
        release_id = response.json()["id"]
        print(f"Gitee release created: {release_id}")
    upload_url = f"{base}/{release_id}/attach_files"
    for path in files:
        with path.open("rb") as handle:
            upload = requests.post(upload_url, params={"access_token": token}, files={"file": handle}, timeout=180)
        if upload.status_code not in (201, 409):
            upload.raise_for_status()
        print(f"Uploaded {path.name}")


if __name__ == "__main__":
    latest_release, release_files = download_latest_release()
    sync_to_gitee(latest_release, release_files)
    print("Sync is completed")
