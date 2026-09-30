"""Part image storage shared by manual upload and import: decode, re-encode to PNG (long edge ≤ 1024 px,
section 15) and store content-addressed as an `asset` row + file."""

from __future__ import annotations

import io
import uuid

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Asset
from app.render.canvas import sha256

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_EDGE = 1024
# Formats accepted from spreadsheet pictures (Excel stores pasted pictures as PNG/JPEG, sometimes GIF/BMP).
PICTURE_FORMATS = ("PNG", "JPEG", "WEBP", "GIF", "BMP")


class PictureError(Exception):
    pass


def to_png(img: Image.Image) -> bytes:
    converted = img.convert("RGBA") if img.mode not in ("RGB", "RGBA", "L", "LA") else img.copy()
    converted.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    converted.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def png_from_picture(data: bytes) -> bytes:
    """A spreadsheet picture -> normalized PNG. Raises PictureError for unreadable or unsupported pictures."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise PictureError
    try:
        with Image.open(io.BytesIO(data), formats=PICTURE_FORMATS) as img:
            img.load()
            return to_png(img)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PictureError from exc


async def store_png(db: AsyncSession, png: bytes, user_id: uuid.UUID) -> Asset:
    """Content-addressed: identical images share one asset row and file."""
    digest = sha256(png)
    asset = (await db.execute(select(Asset).where(Asset.sha256 == digest))).scalar_one_or_none()
    if asset is None:
        key = f"{digest.hex()[:2]}/{digest.hex()}.png"
        path = get_settings().asset_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(png)
        tmp.replace(path)
        asset = Asset(sha256=digest, mime_type="image/png", byte_size=len(png), storage_key=key, created_by=user_id)
        db.add(asset)
        await db.flush()
    return asset
