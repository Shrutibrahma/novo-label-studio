"""Checks the committed render goldens on the current platform without pytest (used to confirm the Linux
container renders byte-identical PNGs to the Windows test run):  python -m tests.golden_check [--pixels]"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import types

sys.modules.setdefault("pytest", types.SimpleNamespace(mark=types.SimpleNamespace(  # type: ignore[arg-type]
    parametrize=lambda *a, **k: (lambda f: f), skip=lambda *a, **k: (lambda f: f))))

from PIL import Image  # noqa: E402

from tests.test_render import GOLDEN_FILE, golden_cases, run  # noqa: E402


def main() -> int:
    if "--pixels" in sys.argv:
        for cid, s, size, qr in golden_cases()[:4]:
            r = run(s, size, qr)
            px = hashlib.sha256(Image.open(io.BytesIO(r.png)).tobytes()).hexdigest()[:16]
            print(cid, "png", r.sha256.hex()[:16], "pixels", px, "bytes", len(r.png))
        import PIL
        import zlib
        print("pillow", PIL.__version__, "zlib", zlib.ZLIB_RUNTIME_VERSION, PIL.features.version("freetype2"))
        return 0
    stored = json.loads(GOLDEN_FILE.read_text())
    bad = [cid for cid, s, size, qr in golden_cases() if run(s, size, qr).sha256.hex() != stored.get(cid)]
    print(f"{len(stored) - len(bad)}/{len(stored)} goldens match" + (f"; differ: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
