"""
Satellite Location Intelligence (BETA)
=======================================

Resolves an approximate location for a project from the location information
that ALREADY exists in the datasets (work description, district, constituency,
state) using the OpenStreetMap Nominatim geocoding service, and reports an
honest confidence level for the match.

HARD RULES
----------
- The `projects` table contains NO coordinates. None are invented here:
  every lat/lon returned comes from a real geocoder response, or the status
  is "unresolved"/"error".
- A match is an ESTIMATE of where recorded financial activity occurred —
  never a verified project site boundary.
- No external API key is required (Nominatim is open); an optional
  NOMINATIM_BASE_URL env var allows self-hosting.
- Outbound calls are rate-limited (>= 1.1 s apart, Nominatim policy) and
  cached in the `geocode_cache` table keyed by the query string, so a
  project is geocoded once — page loads and repeat views never re-call
  the service.
"""

import hashlib
import logging
import os
import re
import threading
import time
from typing import Dict, List, Optional

import requests

import models
from database import SessionLocal

logger = logging.getLogger("mplads.geospatial")

NOMINATIM_BASE = os.environ.get("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org")
USER_AGENT = "MPLADS-Audit-Portal/2.0 (project-audit-geolocation; contact: auditor-portal)"
MIN_INTERVAL_S = 1.1     # Nominatim usage policy: max 1 request/second
REQUEST_TIMEOUT_S = 10

_rate_lock = threading.Lock()
_last_call = 0.0

# ── Project-type usefulness (satellite imagery applicability) ───────────
# Ground-works whose progress is plausibly observable in aerial imagery.
SPATIAL_KEYWORDS = (
    "road", "bridge", "culvert", "build", "school", "college", "hall",
    "playground", "stadium", "park", "tank", "pond", "drain", "canal",
    "check dam", "pathway", "boundary wall", "toilet", "crematorium",
    "bus stand", "bus shed", "bus stop", "anganwadi", "library",
    "community center", "community centre", "market", "warehouse",
    "godown", "waiting shed", "footpath", "kerb", "street light",
    "burial", "smashan", "shamshan", "water supply", "bore well",
    "borewell", "irrigation", "channel", "ghat", "wall", "shed",
    "complex", "building", "room", "classroom", "toilets", "workshop",
)
# Purchases whose "progress" is not observable from above.
NON_SPATIAL_KEYWORDS = (
    "vehicle", "equipment", "furniture", "medical", "ambulance", "hearse",
    "laptop", "computer", "printer", "projector", "smart board", "camera",
    "sound system", "musical", "gym equipment", "water tanker purchase",
    "purchase and supply", "supply of", "septic tank suction", "trs",
    "instrument", "appliance", "generator purchase",
)

GENERIC_DESC_STARTERS = (
    "construction", "con", "construction of", "purchase", "supply",
    "installation", "install", "repair", "renovation", "improvement",
    "upgradation", "providing", "laying", "development", "maintenance",
    "widening", "est", "establishment", "procurement", "furnishing",
)

WARD_RE = re.compile(r"ward\s*(?:no\.?|number)?\s*[:\-]?\s*(\d+[a-z]?)", re.I)


def classify_usefulness(project_type: Optional[str], project_name: Optional[str] = "") -> dict:
    """Is satellite imagery plausibly useful for this project type?"""
    text = f"{project_type or ''} {project_name or ''}".lower()
    if any(k in text for k in NON_SPATIAL_KEYWORDS) and not any(k in text for k in SPATIAL_KEYWORDS):
        return {
            "usefulness": "limited",
            "note": "Satellite verification has limited applicability for this project type "
                    "(purchased goods/equipment are not observable in aerial imagery).",
        }
    if any(k in text for k in SPATIAL_KEYWORDS):
        return {
            "usefulness": "high",
            "note": "Ground infrastructure of this kind is generally observable in satellite imagery.",
        }
    return {
        "usefulness": "limited",
        "note": "Satellite verification may have limited applicability for this project type. "
                "Manual verification is recommended regardless.",
    }


def _clean_segment(seg: str) -> str:
    seg = re.sub(r"\s+", " ", seg).strip(" ,;:-")
    return seg


def _is_generic(seg: str) -> bool:
    low = seg.lower()
    return any(low.startswith(g) for g in GENERIC_DESC_STARTERS) or len(low) < 3


def extract_location_query(project) -> dict:
    """
    Build the best possible geocoding query from ACTUAL project fields.

    Priority: specific place names in the work description (after 'at'/'near'/
    'in', and comma-separated trailing segments), ward numbers, then
    district/city, constituency, state. Generic verb phrases are excluded.
    """
    desc = str(getattr(project, "project_name", "") or "")
    state = str(getattr(project, "state", "") or "") or None
    district = str(getattr(project, "district", "") or "") or None
    constituency = str(getattr(project, "constituency", "") or "") or None

    specific_parts: List[str] = []
    ward = None

    # "Ward No.18" anywhere in the description
    wm = WARD_RE.search(desc)
    if wm:
        ward = f"Ward {wm.group(1)}"

    # Specific place after ' at ' / ' near ' / ' in '
    m = re.search(r"\b(?:at|near|in)\s+(.+)$", desc, re.I)
    tail = _clean_segment(m.group(1)) if m else ""
    if tail and not _is_generic(tail.split(",")[0]):
        for seg in tail.split(","):
            seg = _clean_segment(seg)
            if not seg or _is_generic(seg):
                continue
            specific_parts.append(seg)

    # Fallback: trailing comma segments of the description (common pattern:
    # "... , <Village>, Ward No.X, <Town>")
    if not specific_parts:
        segs = [_clean_segment(s) for s in desc.split(",")]
        segs = [s for s in segs if s and not _is_generic(s)]
        # keep at most the last three segments (they are usually the place chain)
        specific_parts = segs[-3:] if len(segs) > 3 else segs

    # Drop pure ward segments from the place list (kept separately)
    place_parts = [p for p in specific_parts if not WARD_RE.search(p)]
    # A segment that is only "Ward ..." adds no geocoding value on its own

    place = ", ".join(place_parts[:3]) if place_parts else None

    components = {
        "place": place,
        "ward": ward,
        "district": district,
        "constituency": constituency,
        "state": state,
    }

    # Primary query: most specific first, administrative context after.
    primary_bits = [b for b in [place, district or constituency, state] if b]
    primary = ", ".join(primary_bits) if primary_bits else None

    # Fallback query (used only if primary resolves nothing): less specific.
    fallback_bits = [b for b in [constituency, district, state] if b]
    fallback = ", ".join(fallback_bits) if fallback_bits else None

    return {
        "primary_query": primary,
        "fallback_query": fallback,
        "components": components,
        "specificity": "specific" if place else ("administrative" if fallback else "none"),
    }


# ── Geocoding (Nominatim) ────────────────────────────────────────────────

def _throttle():
    """Serialize outbound calls, >= MIN_INTERVAL_S apart (shared across threads)."""
    global _last_call
    with _rate_lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _nominatim_search(query: str) -> List[dict]:
    _throttle()
    try:
        resp = requests.get(
            f"{NOMINATIM_BASE}/search",
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 5,
                "countrycodes": "in",  # MPLADS is India-only; improves precision
            },
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json() or []
    except Exception as exc:
        logger.warning("Nominatim search failed for %r: %s", query, exc)
        raise


def _bbox_extent_deg(result: dict) -> Optional[float]:
    bb = result.get("boundingbox")
    try:
        south, north, west, east = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
        return max(north - south, east - west)
    except (TypeError, ValueError, IndexError):
        return None


def _state_matches(result: dict, state: Optional[str]) -> Optional[bool]:
    if not state:
        return None
    addr = (result.get("address") or {})
    norm = re.sub(r"[^a-z]", "", state.lower())
    for v in (addr.get("state"), addr.get("state_district"), addr.get("region")):
        if v and re.sub(r"[^a-z]", "", v.lower()) and (
            norm in re.sub(r"[^a-z]", "", v.lower()) or re.sub(r"[^a-z]", "", v.lower()) in norm
        ):
            return True
    return False


def _score_results(results: List[dict], state: Optional[str]) -> dict:
    """
    Pick the best candidate honestly: rank by importance; check divergence
    between top candidates; assign confidence with explainable rules.
    """
    if not results:
        return {"status": "unresolved", "confidence": "Unresolved",
                "reason": "No matching location found for the available project fields."}

    ranked = sorted(results, key=lambda r: (r.get("importance") or 0), reverse=True)
    top = ranked[0]
    extent = _bbox_extent_deg(top)
    importance = float(top.get("importance") or 0)
    st_match = _state_matches(top, state)

    addr = top.get("address") or {}
    precise_type = top.get("type") in (
        "village", "hamlet", "suburb", "neighbourhood", "quarter",
        "road", "residential", "building", "house", "primary", "secondary",
    )

    # Divergence: if another similarly-important candidate is far away,
    # the location is ambiguous.
    ambiguous = False
    if len(ranked) > 1:
        for other in ranked[1:3]:
            try:
                dlat = abs(float(top["lat"]) - float(other["lat"]))
                dlon = abs(float(top["lon"]) - float(other["lon"]))
                if max(dlat, dlon) > 0.5 and abs((other.get("importance") or 0) - importance) < 0.15:
                    ambiguous = True
                    break
            except (KeyError, ValueError, TypeError):
                continue

    if extent is not None and extent <= 0.05 and importance >= 0.25 and precise_type and st_match is not False:
        confidence, reason = "High", "Matched a specific place (village/ward/locality level) within the correct state."
    elif (extent is not None and extent <= 0.3) or (importance >= 0.3 and st_match is not False):
        confidence, reason = "Medium", "Matched at town/city level; the exact work site may differ."
    else:
        confidence, reason = "Low", "Only an approximate administrative-area match was found."
    if ambiguous:
        confidence = "Low"
        reason = "Multiple possible locations found. Manual verification recommended."
    elif st_match is False and confidence == "High":
        confidence = "Medium"
        reason += " State field did not match exactly; verify the result."

    return {
        "status": "resolved",
        "confidence": confidence,
        "confidence_reason": reason,
        "match": {
            "lat": float(top["lat"]),
            "lon": float(top["lon"]),
            "display_name": top.get("display_name"),
            "type": top.get("type"),
            "class": top.get("class"),
            "importance": round(importance, 3),
            "bbox_extent_deg": round(extent, 5) if extent is not None else None,
        },
        "candidates_considered": len(results),
        "ambiguous": ambiguous,
    }


# ── Cache ────────────────────────────────────────────────────────────────

def _query_hash(query: str) -> str:
    return hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()


def _cache_get(query: str) -> Optional[dict]:
    db = SessionLocal()
    try:
        row = (
            db.query(models.GeocodeCache)
            .filter(models.GeocodeCache.query_hash == _query_hash(query))
            .first()
        )
        if not row:
            return None
        import json
        try:
            return json.loads(row.payload)
        except Exception:
            return None
    finally:
        db.close()


def _cache_put(query: str, payload: dict) -> None:
    import json
    db = SessionLocal()
    try:
        h = _query_hash(query)
        existing = db.query(models.GeocodeCache).filter(models.GeocodeCache.query_hash == h).first()
        if not existing:
            db.add(models.GeocodeCache(
                query_hash=h,
                query=query,
                payload=json.dumps(payload),
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ))
            db.commit()
    except Exception as exc:  # caching must never break the response
        db.rollback()
        logger.warning("Geocode cache write failed: %s", exc)
    finally:
        db.close()


# ── Public API ───────────────────────────────────────────────────────────

def get_project_geolocation(project) -> dict:
    """
    Full Satellite-Location-Intelligence payload for one project.

    Never raises: failures become status='error' so the UI can offer Retry.
    """
    usefulness = classify_usefulness(
        getattr(project, "project_type", None),
        getattr(project, "project_name", "") or "",
    )
    extraction = extract_location_query(project)

    base = {
        "beta": True,
        "project_id": project.id,
        "extraction": extraction,
        "usefulness": usefulness,
        "provider": "OpenStreetMap Nominatim",
        "categories": {
            "source_data": "Values taken directly from MPLADS datasets (work description, district, constituency, state).",
            "geocoded": "Coordinates derived from those fields via a public geocoding service — an estimate, not a surveyed site location.",
            "satellite": "External aerial imagery provided as visual reference only.",
            "inference": "Confidence labels and usefulness guidance are system-generated interpretations.",
        },
        "disclaimer": (
            "Satellite imagery is provided as visual reference only. It does not independently "
            "verify project completion. Field verification remains necessary."
        ),
    }

    if extraction["specificity"] == "none":
        return {
            **base,
            "status": "unavailable",
            "confidence": "Unresolved",
            "confidence_reason": "Insufficient location information to confidently resolve the project.",
            "match": None,
        }

    tried = []
    for query in [extraction["primary_query"], extraction["fallback_query"]]:
        if not query:
            continue
        tried.append(query)
        cached = _cache_get(query)
        if cached is not None:
            result = dict(cached)
            result["cached"] = True
            result["queries_tried"] = tried
            return {**base, **result}
        try:
            results = _nominatim_search(query)
        except Exception as exc:
            return {
                **base,
                "status": "error",
                "confidence": "Unresolved",
                "confidence_reason": "The geocoding service could not be reached. Please retry.",
                "error": str(exc)[:200],
                "queries_tried": tried,
                "match": None,
            }
        scored = _score_results(results, extraction["components"].get("state"))
        payload = {**scored, "queries_tried": tried, "cached": False}
        if scored["status"] == "resolved":
            _cache_put(query, payload)
            return {**base, **payload}
        # unresolved with this query — try the fallback before giving up

    return {
        **base,
        "status": "unresolved",
        "confidence": "Unresolved",
        "confidence_reason": "Location could not be reliably resolved from the available project fields.",
        "queries_tried": tried,
        "match": None,
    }
