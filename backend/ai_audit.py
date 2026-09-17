"""
AI Audit — Computer-Vision & Forensic Helpers (SIH 26102)
=========================================================

Pure-Pillow implementations used by the /ai/* audit endpoints:

- dHash (difference hash) perceptual fingerprinting of progress photos,
  with Hamming distance based duplicate detection.
- EXIF GPS extraction + haversine distance so an uploaded field photo can
  be checked against the project's recorded site coordinates.

Design constraints (512MB Render instance):
- Images are decoded one at a time, downscaled to 9x9 grayscale
  immediately, and released — no image ever stays in memory.
- dHash keys are 64-bit integers stored as strings; the duplicate index
  is a single streamed pass over the photo_hashes table.
- All "fraud signals" here are heuristic similarity/distance measures,
  reported with their numeric evidence. Nothing claims legal proof.
"""

import io
import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# PIL is imported lazily on first image use — importing it eagerly pinned
# ~15-20 MB of image-codec modules in every backend process (including the
# Render free instance) even when no image was ever uploaded.
Image = None
ImageOps = None


def _ensure_pil():
    global Image, ImageOps
    if Image is not None:
        return
    from PIL import Image as _Image, ImageOps as _ImageOps
    # Remove the embedded thumbnail that can carry stripped EXIF ghost data
    # and keeps large images in memory longer than needed.
    _Image.LOAD_TRUNCATED_IMAGES = False
    _Image.MAX_IMAGE_PIXELS = 64_000_000  # decompression-bomb guard (~64MP)
    Image, ImageOps = _Image, _ImageOps


DHASH_BITS = 64


# ────────────────────────────────────────────────────────────────────
# Perceptual hashing (dHash 64-bit)
# ────────────────────────────────────────────────────────────────────

def dhash64(file_bytes: bytes) -> Optional[str]:
    """Return the 64-bit dHash of an image as a hex string, or None."""
    _ensure_pil()
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        # dHash: 9x wide, 8 tall grayscale → 8x8 = 64 horizontal gradients.
        img = img.convert("L").resize((9, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        rows = [pixels[i * 9:(i + 1) * 9] for i in range(8)]
        bits = 0
        for row in rows:
            for x in range(8):
                bits = (bits << 1) | (1 if row[x] > row[x + 1] else 0)
        return f"{bits:016x}"
        # img is released when this frame ends; only the 16-char key survives.
    except Exception:
        return None


def hamming_hex(a: str, b: str) -> int:
    """Hamming distance between two equal-length hex dHash strings."""
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (ValueError, TypeError):
        return DHASH_BITS  # maximally different on parse failure


def similarity_from_distance(distance: int) -> float:
    return round((1 - distance / DHASH_BITS) * 100, 1)


# ────────────────────────────────────────────────────────────────────
# EXIF GPS
# ────────────────────────────────────────────────────────────────────

def _to_degrees(ratio) -> Optional[float]:
    try:
        d = float(ratio[0])
        m = float(ratio[1])
        s = float(ratio[2])
        if m == 0 and s == 0:
            return None
        return d + m / 60.0 + s / 3600.0
    except Exception:
        return None


def extract_exif_gps(file_bytes: bytes) -> Dict:
    """Extract GPS coordinates + capture metadata from EXIF, honestly.

    Returns {has_gps, lat, lon, captured_at, camera, stripped}.
    `stripped` is True when the file has no usable EXIF block at all —
    a signal auditors care about (common when photos are re-saved through
    messengers/screenshots), but it is reported, never fabricated.
    """
    _ensure_pil()
    out: Dict = {
        "has_gps": False, "lat": None, "lon": None,
        "captured_at": None, "camera": None, "stripped": True,
    }
    try:
        img = Image.open(io.BytesIO(file_bytes))
        exif = img.getexif()
        if not exif:
            return out
        out["stripped"] = False
        # 0x8825 = GPSInfo IFD pointer; 0x8769 = Exif IFD pointer
        gps_ifd = exif.get_ifd(0x8825)
        exif_ifd = exif.get_ifd(0x8769)
        if gps_ifd:
            lat_ref = gps_ifd.get(1)          # 'N'/'S'
            lat = _to_degrees(gps_ifd.get(2))
            lon_ref = gps_ifd.get(3)          # 'E'/'W'
            lon = _to_degrees(gps_ifd.get(4))
            if lat is not None and lon is not None:
                if str(lat_ref).upper() == "S":
                    lat = -lat
                if str(lon_ref).upper() == "J" or str(lon_ref).upper() == "W":
                    lon = -lon
                out.update(has_gps=True, lat=round(lat, 6), lon=round(lon, 6))
        dt = exif_ifd.get(0x9003) or exif_ifd.get(0x9004)  # DateTimeOriginal / -Digitized
        if dt:
            out["captured_at"] = str(dt)
        make = exif.get(0x010F)  # Make
        model = exif.get(0x0110)  # Model
        if make or model:
            out["camera"] = f"{make or ''} {model or ''}".strip()
        return out
    except Exception:
        return out


def haversine_m(lat1, lon1, lat2, lon2) -> Optional[float]:
    """Great-circle distance in metres; None if any coordinate missing."""
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


# ────────────────────────────────────────────────────────────────────
# Risk banding shared by the audit queue / inspection modal
# ────────────────────────────────────────────────────────────────────

def risk_band(score: int) -> Tuple[str, str]:
    """(band, severity) for a 0-100 audit risk index."""
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    if score >= 80:
        return "Critical", "red"
    if score >= 50:
        return "Moderate", "yellow"
    return "Low", "green"


# ────────────────────────────────────────────────────────────────────
# Category normalization for cost benchmarking
# ────────────────────────────────────────────────────────────────────

def norm_category(raw: Optional[str]) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return "other"
    if "road" in s or "bridge" in s or "culvert" in s:
        return "road_infra"
    if "building" in s or "hall" in s or "school" in s or "anganwadi" in s:
        return "buildings"
    if "water" in s or "drain" in s or "bore" in s or "well" in s:
        return "water_sanitation"
    if "solar" in s or "light" in s or "electric" in s:
        return "electrical"
    if "playground" in s or "park" in s or "gym" in s:
        return "public_amenities"
    if "furniture" in s or "equipment" in s or "computer" in s or "vehicle" in s:
        return "goods_equipment"
    return "other"


def sample_size_penalty(n: int) -> float:
    """Shrink factor for benchmarks built on tiny regional samples."""
    if n <= 0:
        return 0.0
    return n / (n + 5.0)   # 5 pseudo-observations — mild shrinkage
