"""Download an MLX Whisper model from ModelScope into backend/models/.

For networks where huggingface.co is unreachable. Resumable, and every file
is verified against the SHA-256 published by ModelScope.

    uv run python scripts/download_asr_model.py [mlx-community/whisper-large-v3-turbo]

Then set ASR_MODEL=models/whisper-large-v3-turbo (relative to backend/).
"""

import hashlib
import sys
from pathlib import Path

import httpx

API = "https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Revision=master&Recursive=true"
FILE = "https://www.modelscope.cn/models/{repo}/resolve/master/{path}"
NEEDED = {"config.json", "weights.safetensors", "weights.npz"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download(client: httpx.Client, url: str, dest: Path, size: int) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with client.stream("GET", url, headers=headers, follow_redirects=True) as r:
        r.raise_for_status()
        if have and r.status_code != 206:  # server ignored Range: start over
            have = 0
        with part.open("ab" if have else "wb") as f:
            done = have
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {dest.name}: {done / 1e6:,.0f} / {size / 1e6:,.0f} MB", end="", flush=True)
    print()
    part.rename(dest)


def main(repo: str) -> None:
    out = Path(__file__).resolve().parent.parent / "models" / repo.split("/")[-1]
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(60, read=120)) as client:
        files = client.get(API.format(repo=repo)).raise_for_status().json()["Data"]["Files"]
        # config.json last: its presence is what marks the folder as usable.
        for f in sorted(files, key=lambda f: f["Path"] == "config.json"):
            if f["Path"] not in NEEDED:
                continue
            dest = out / f["Path"]
            if dest.exists() and sha256(dest) == f["Sha256"]:
                print(f"  {dest.name}: already verified")
                continue
            download(client, FILE.format(repo=repo, path=f["Path"]), dest, f["Size"])
            if sha256(dest) != f["Sha256"]:
                dest.unlink()
                sys.exit(f"Checksum mismatch for {dest.name}; deleted. Run again.")
            print(f"  {dest.name}: sha256 OK")
    print(f"Done. Set ASR_MODEL={out.relative_to(out.parent.parent)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mlx-community/whisper-large-v3-turbo")
