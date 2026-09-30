"""Decodes the ZPL this system produces (spec 8.1) back into images.

Used by the SimulatedPrinter to write a PNG of every label, and as a dev tool to check visually that a .zpl
file matches the preview without a printer:

    uv run zpl2png agent-output/<job>.zpl            # writes <job>-1.png, <job>-2.png, ... next to it
    uv run zpl2png some.zpl --out C:\\tmp\\labels
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_INVERT = bytes(b ^ 0xFF for b in range(256))
_LABEL = re.compile(rb"\^XA(.*?)\^XZ", re.S)
_GFA = re.compile(rb"\^FO(\d+),(\d+)\^GFA,(\d+),(\d+),(\d+),([0-9A-Fa-f]*)\^FS")
_PW = re.compile(rb"\^PW(\d+)")
_LL = re.compile(rb"\^LL(\d+)")
_PQ = re.compile(rb"\^PQ(\d+)")


class ZplError(ValueError):
    pass


@dataclass
class DecodedLabel:
    image: Image.Image  # mode "1": white = 1, like the API's bitmaps
    copies: int
    width_dots: int
    height_dots: int


def decode_label(body: bytes) -> DecodedLabel:
    pw, ll, gfa = _PW.search(body), _LL.search(body), _GFA.search(body)
    if not (pw and ll and gfa):
        raise ZplError("label without ^PW, ^LL or ^GFA")
    width, height = int(pw[1]), int(ll[1])
    x, y, n, n2, bpr = int(gfa[1]), int(gfa[2]), int(gfa[3]), int(gfa[4]), int(gfa[5])
    data = bytes.fromhex(gfa[6].decode("ascii"))
    if n != n2 or len(data) != n or n % bpr:
        raise ZplError(f"^GFA byte count mismatch: header {n}/{n2}, data {len(data)}, bpr {bpr}")
    rows = n // bpr
    field = Image.frombytes("1", (bpr * 8, rows), data.translate(_INVERT))
    canvas = Image.new("1", (width, height), 1)
    canvas.paste(field.crop((0, 0, min(bpr * 8, width - x), min(rows, height - y))), (x, y))
    pq = _PQ.search(body)
    return DecodedLabel(image=canvas, copies=int(pq[1]) if pq else 1, width_dots=width, height_dots=height)


def decode(zpl: bytes) -> list[DecodedLabel]:
    labels = [decode_label(m[1]) for m in _LABEL.finditer(zpl)]
    if not labels:
        raise ZplError("no ^XA … ^XZ label found")
    return labels


def write_pngs(zpl: bytes, out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, label in enumerate(decode(zpl), start=1):
        path = out_dir / f"{stem}-{i}.png"
        label.image.save(path, format="PNG")
        paths.append(path)
    return paths


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="zpl2png", description="Decode Smart Labels ZPL (^GFA) back to PNG images.")
    p.add_argument("file", type=Path)
    p.add_argument("--out", type=Path, default=None, help="output folder (default: next to the .zpl file)")
    args = p.parse_args(argv)
    try:
        data = args.file.read_bytes()
        paths = write_pngs(data, args.out or args.file.parent, args.file.stem)
    except (OSError, ZplError) as exc:
        print(f"zpl2png: {exc}", file=sys.stderr)
        return 1
    for path, label in zip(paths, decode(data), strict=True):
        print(f"{path}  ({label.width_dots} x {label.height_dots} dots, copies {label.copies})")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
