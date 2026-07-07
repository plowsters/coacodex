"""One-shot: download the WOFF2 files the guide CSS @font-faces into coa_meta/assets/fonts/."""
from __future__ import annotations
import re, urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "coa_meta" / "assets" / "fonts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
FACES = {
    "Cinzel:wght@600;700;900": "Cinzel",
    "Barlow:wght@400;500;600;700": "Barlow",
    "JetBrains+Mono:wght@500;700": "JetBrainsMono",
}

def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA})).read()

def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for spec, family in FACES.items():
        css = fetch(f"https://fonts.googleapis.com/css2?family={spec}&display=swap").decode("utf-8")
        for i, (weight, woff) in enumerate(re.findall(r"font-weight:\s*(\d+);[^}]*?src:\s*url\(([^)]+\.woff2)\)", css, re.S)):
            data = fetch(woff)
            out = DEST / f"{family}-{weight}.woff2"
            out.write_bytes(data)
            print("wrote", out, len(data), "bytes")

if __name__ == "__main__":
    main()
