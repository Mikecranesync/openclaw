"""Knowledge Base enrichment pipeline.

Four-stage pipeline that turns a component photo into a KB atom:

    Photo arrives
        │
        ▼
    [INGEST]     ─── Vision OCR: extract vendor, product, terminals, ratings
        │
        ▼
    [AUGMENT]    ─── Search existing KB for matching manuals / specs
        │
        ▼
    [SYNTHESIZE] ─── Normalize into canonical wiring representation
        │
        ▼
    [UPSERT]     ─── Insert new atom or update existing (dual-write)

Entry point: enrich_from_photo(photo_path, tags=None)
Legacy entry: enrich_from_project(project) — batch enrichment from reconstruction
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from openclaw.wiring.models import ComponentRecord, WiringProject

log = logging.getLogger(__name__)

# Singleton sync KB connector for enrichment pipeline
_sync_kb = None

def _get_sync_kb():
    """Get or create a sync KnowledgeConnector for the enrichment pipeline.

    Reads DB config from openclaw.yaml or env vars.
    """
    global _sync_kb
    if _sync_kb is not None:
        return _sync_kb

    import os

    # Try to read from openclaw.yaml first (VPS deployment)
    db_url = None
    try:
        import yaml
        for config_path in ['/opt/openclaw/openclaw.yaml', 'openclaw.yaml']:
            try:
                with open(config_path) as f:
                    cfg = yaml.safe_load(f)
                db_url = cfg.get('openclaw', {}).get('kb_postgres_url')
                if db_url:
                    break
            except FileNotFoundError:
                continue
    except ImportError:
        pass

    # Fall back to env vars
    if not db_url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "rivet")
        user = os.getenv("POSTGRES_USER", "rivet")
        pw = os.getenv("POSTGRES_PASSWORD", "rivet_factory_2025!")
        db_url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)

        # Minimal sync wrapper matching the enrichment pipeline's needs
        class SyncKB:
            def __init__(self, connection):
                self._conn = connection

            def find_by_part(self, vendor, part_number):
                try:
                    cur = self._conn.cursor()
                    cur.execute(
                        """SELECT atom_id, atom_type, vendor, product, title, summary, content,
                                  keywords, part_number, wiring_model, manual_refs, provenance,
                                  needs_review
                           FROM knowledge_atoms
                           WHERE vendor ILIKE %s AND (product ILIKE %s OR part_number ILIKE %s)
                           LIMIT 1""",
                        [f"%{vendor}%", f"%{part_number}%", f"%{part_number}%"]
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    columns = [desc[0] for desc in cur.description]
                    return dict(zip(columns, row))
                except Exception as e:
                    log.debug("find_by_part failed: %s", e)
                    self._conn.rollback()
                    return None

            def search(self, query, vendor=None, limit=5):
                try:
                    cur = self._conn.cursor()
                    sql = """SELECT atom_id, atom_type, vendor, product, title,
                                    LEFT(summary, 500) as summary, content, keywords
                             FROM knowledge_atoms
                             WHERE to_tsvector('english', title || ' ' || summary || ' ' || content)
                                   @@ plainto_tsquery('english', %s)
                             ORDER BY ts_rank(
                                 to_tsvector('english', title || ' ' || summary || ' ' || content),
                                 plainto_tsquery('english', %s)) DESC
                             LIMIT %s"""
                    cur.execute(sql, [query, query, limit])
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
                except Exception as e:
                    log.debug("search failed: %s", e)
                    self._conn.rollback()
                    return []

            def insert_atom(self, atom_data):
                try:
                    import json as _json
                    cur = self._conn.cursor()
                    cur.execute(
                        """INSERT INTO knowledge_atoms (
                                atom_type, vendor, product, part_number, title, summary, content,
                                keywords, wiring_model, manual_refs, provenance, needs_review
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING atom_id""",
                        [
                            atom_data.get("atom_type", "spec"),
                            atom_data.get("vendor", ""),
                            atom_data.get("product", ""),
                            atom_data.get("part_number", ""),
                            atom_data.get("title", ""),
                            atom_data.get("summary", ""),
                            atom_data.get("content", "")[:5000],
                            atom_data.get("keywords", []),
                            _json.dumps(atom_data.get("wiring_model", {})),
                            atom_data.get("manual_refs", []),
                            _json.dumps(atom_data.get("provenance", [])),
                            atom_data.get("needs_review", False),
                        ]
                    )
                    atom_id = cur.fetchone()[0]
                    self._conn.commit()
                    return atom_id
                except Exception as e:
                    log.error("insert_atom failed: %s", e)
                    self._conn.rollback()
                    return None

            def update_atom(self, atom_id, updates, provenance=None, conflict=False):
                try:
                    import json as _json
                    cur = self._conn.cursor()
                    cur.execute(
                        """UPDATE knowledge_atoms SET
                                summary = COALESCE(%s, summary),
                                content = COALESCE(%s, content),
                                keywords = COALESCE(%s, keywords),
                                wiring_model = COALESCE(%s, wiring_model),
                                needs_review = %s
                            WHERE atom_id = %s""",
                        [
                            updates.get("summary"),
                            updates.get("content"),
                            updates.get("keywords"),
                            _json.dumps(updates["wiring_model"]) if "wiring_model" in updates else None,
                            conflict,
                            atom_id,
                        ]
                    )
                    self._conn.commit()
                    return True
                except Exception as e:
                    log.error("update_atom failed: %s", e)
                    self._conn.rollback()
                    return False

        _sync_kb = SyncKB(conn)
        log.info("Sync KB connector initialized from %s", db_url.split("@")[-1])
        return _sync_kb
    except ImportError:
        log.warning("psycopg2 not installed — KB upsert disabled")
        return None
    except Exception as e:
        log.error("Sync KB connection failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EnrichmentResult:
    """Result from the enrichment pipeline."""

    atom_id: Optional[int] = None
    vendor: str = ""
    product: str = ""
    part_number: str = ""
    component_type: str = ""
    is_new: bool = False
    was_updated: bool = False
    needs_review: bool = False
    summary: str = ""
    raw_vision: dict = field(default_factory=dict)
    raw_kb_matches: list = field(default_factory=list)
    atom_data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Vision prompt for component enrichment (separate from reconstruction)
# ---------------------------------------------------------------------------

ENRICHMENT_SYSTEM_PROMPT = (
    "You are an expert industrial electrician analyzing a close-up photograph "
    "of an electrical component. Extract all visible data from the nameplate, "
    "terminals, and any markings. Be precise — only report what you can see."
)

ENRICHMENT_USER_PROMPT = """Analyze this close-up photo of an electrical component.

Extract everything visible:
1. **Nameplate**: manufacturer, product name, part number, catalog number
2. **Ratings**: voltage, current, power, frequency, coil voltage, trip range
3. **Terminals**: numbered terminal IDs visible on the device
4. **Component type**: What kind of device is this? (contactor, overload relay, circuit breaker, VFD, motor starter, transformer, terminal block, sensor, switch, indicator, fuse, etc.)
5. **Any wiring diagram** printed on the device itself

RESPOND IN JSON ONLY:
{{
  "vendor": "manufacturer name",
  "product": "product name or series",
  "part_number": "exact part/catalog number",
  "component_type": "type of device",
  "ratings": {{
    "voltage": "rated voltage or null",
    "current": "rated current or null",
    "power": "rated power or null",
    "frequency": "frequency or null",
    "coil_voltage": "coil voltage or null",
    "trip_range": "overload trip range or null"
  }},
  "terminals": {{
    "1": {{"label": "L1 or description"}},
    "2": {{"label": "T1 or description"}}
  }},
  "wiring_diagram": {{
    "coil_terminals": ["A1", "A2"],
    "power_poles": [["1","2"], ["3","4"], ["5","6"]],
    "aux_contacts": [["13","14"]],
    "notes": "any diagram text"
  }},
  "additional_text": "any other text visible on the component",
  "confidence": 0.8
}}

IMPORTANT:
- Only report what you can actually READ on the component.
- If a field is not visible, use null.
- Terminal labels like L1/T1 are standard IEC designations."""


# ---------------------------------------------------------------------------
# Stage 1: INGEST — Vision OCR on the photo
# ---------------------------------------------------------------------------

def _ingest_photo(photo_path: str, tags: Optional[str] = None) -> dict:
    """Run vision OCR on a component photo.

    Returns extracted data dict from the vision LLM.
    """
    path = Path(photo_path)
    if not path.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    photo_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    ext = path.suffix.lower()
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")

    user_prompt = ENRICHMENT_USER_PROMPT
    if tags:
        user_prompt += f"\n\nHINT: The component may be tagged as: {tags}"

    # Try OpenRouter first (most reliable), then Gemini, then Claude
    try:
        return _call_openrouter_vision(photo_b64, mime_type, user_prompt)
    except Exception as e:
        log.warning("OpenRouter enrichment call failed: %s — trying Gemini", e)

    try:
        return _call_gemini_vision(photo_b64, mime_type, user_prompt)
    except Exception as e:
        log.warning("Gemini enrichment call failed: %s — trying Claude", e)

    try:
        return _call_claude_vision(photo_b64, mime_type, user_prompt)
    except Exception as e:
        log.warning("Claude enrichment call failed: %s — returning empty", e)

    return {
        "vendor": "",
        "product": "",
        "part_number": "",
        "component_type": "",
        "ratings": {},
        "terminals": {},
        "wiring_diagram": {},
        "confidence": 0.0,
    }


def _call_gemini_vision(photo_b64: str, mime_type: str, user_prompt: str) -> dict:
    """Call Google Gemini for component OCR."""
    import os

    import google.generativeai as genai  # type: ignore

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        system_instruction=ENRICHMENT_SYSTEM_PROMPT,
    )

    image_bytes = base64.b64decode(photo_b64)
    response = model.generate_content(
        [
            {"mime_type": mime_type, "data": image_bytes},
            user_prompt,
        ],
        generation_config={"response_mime_type": "application/json"},
    )

    return _repair_and_parse_json(response.text)


def _repair_and_parse_json(text: str) -> dict:
    """Parse JSON with repair for common LLM output issues."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        # Remove optional language tag
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    # Try again after stripping
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Replace single quotes with double quotes (common Gemini issue)
    import re as _re
    try:
        # Only replace quotes that look like JSON keys/values
        fixed = _re.sub(r"(?<=[:,\[{])\s*'", ' "', cleaned)
        fixed = _re.sub(r"'\s*(?=[,\]}: ])", '"', fixed)
        return json.loads(fixed)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to extract JSON object from surrounding text
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    log.warning("JSON repair failed, returning empty dict. Raw: %s", text[:200])
    return {
        "vendor": "",
        "product": "",
        "part_number": "",
        "component_type": "",
        "ratings": {},
        "terminals": {},
        "wiring_diagram": {},
        "confidence": 0.0,
    }


def _call_claude_vision(photo_b64: str, mime_type: str, user_prompt: str) -> dict:
    """Call Anthropic Claude for component OCR."""
    import os

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    media_type = mime_type if mime_type != "image/jpg" else "image/jpeg"

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=ENRICHMENT_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": photo_b64,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ],
    )

    text = response.content[0].text
    return _repair_and_parse_json(text)


def _call_openrouter_vision(photo_b64: str, mime_type: str, user_prompt: str) -> dict:
    """Call OpenRouter (Claude Sonnet) for component OCR."""
    import os

    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/Mikecranesync/openclaw",
            "X-Title": "OpenClaw",
        },
    )

    media_type = mime_type if mime_type != "image/jpg" else "image/jpeg"

    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{photo_b64}"},
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ],
    )

    text = response.choices[0].message.content or ""
    return _repair_and_parse_json(text)



# ---------------------------------------------------------------------------
# Stage 2: AUGMENT — search existing KB for matching data
# ---------------------------------------------------------------------------

def _augment_from_kb(vision_data: dict) -> list[dict]:
    """Search the KB for existing data that augments what vision found.

    Returns list of matching KB records (may be empty).
    """
    vendor = vision_data.get("vendor", "")
    part_number = vision_data.get("part_number", "")
    product = vision_data.get("product", "")

    if not vendor and not part_number:
        return []

    try:
        kb = _get_sync_kb()
        if not kb:
            return []

        # Try exact part lookup first
        if vendor and part_number:
            exact = kb.find_by_part(vendor, part_number)
            if exact:
                return [exact]

        # Fall back to full-text search
        search_terms = " ".join(filter(None, [vendor, product, part_number]))
        if search_terms:
            results = kb.search(search_terms, vendor=vendor, limit=3)
            return results

    except Exception as e:
        log.debug("KB augment search failed: %s", e)

    return []


# ---------------------------------------------------------------------------
# Stage 3: SYNTHESIZE — normalize into canonical atom representation
# ---------------------------------------------------------------------------

def _synthesize(
    vision_data: dict,
    kb_matches: list[dict],
    photo_path: str,
    photo_id: Optional[str] = None,
) -> dict:
    """Merge vision data + KB data into a canonical atom dict.

    Priority: vision data wins for things that are visible (nameplate),
    KB data fills in things that aren't visible (standard terminal labels,
    full wiring models from manuals).
    """
    # Start from vision data
    vendor = vision_data.get("vendor", "")
    product = vision_data.get("product", "")
    part_number = vision_data.get("part_number", "")
    component_type = vision_data.get("component_type", "")
    ratings = vision_data.get("ratings", {})
    terminals = vision_data.get("terminals", {})
    wiring_diagram = vision_data.get("wiring_diagram", {})

    # Merge KB data if available
    existing_atom_id = None
    conflict = False
    kb_manual_refs = []
    kb_keywords = []

    for kb_rec in kb_matches:
        existing_atom_id = kb_rec.get("atom_id")

        # Fill missing fields from KB
        if not vendor and kb_rec.get("vendor"):
            vendor = kb_rec["vendor"]
        if not product and kb_rec.get("product"):
            product = kb_rec["product"]
        if not part_number and kb_rec.get("part_number"):
            part_number = kb_rec["part_number"]

        # Merge terminal layouts from KB (KB has standard terminal labels)
        kb_wiring = kb_rec.get("wiring_model", {})
        if isinstance(kb_wiring, str):
            try:
                kb_wiring = json.loads(kb_wiring)
            except (json.JSONDecodeError, TypeError):
                kb_wiring = {}

        if kb_wiring and not wiring_diagram:
            wiring_diagram = kb_wiring
        elif kb_wiring and wiring_diagram:
            # Both have wiring data — check for conflicts
            if kb_wiring != wiring_diagram:
                conflict = True
                log.info("Wiring model conflict for %s %s", vendor, part_number)

        # Merge ratings
        kb_content = kb_rec.get("content", "")
        if isinstance(ratings, dict):
            for key in ("voltage", "current", "power", "frequency", "coil_voltage"):
                if not ratings.get(key) and key in str(kb_content):
                    # We could parse but it's unreliable — just note it
                    pass

        # Collect manual refs and keywords
        if kb_rec.get("manual_refs"):
            kb_manual_refs.extend(kb_rec["manual_refs"])
        if kb_rec.get("keywords"):
            kw = kb_rec["keywords"]
            if isinstance(kw, list):
                kb_keywords.extend(kw)
            elif isinstance(kw, str):
                kb_keywords.extend(kw.split(","))

    # Clean up ratings — remove None values
    clean_ratings = {}
    if isinstance(ratings, dict):
        clean_ratings = {k: v for k, v in ratings.items() if v}

    # Build keywords
    keywords = list(set(filter(None, [
        part_number,
        vendor,
        component_type,
        product,
    ] + kb_keywords)))

    # Build wiring_model from diagram + terminals
    wiring_model = wiring_diagram if isinstance(wiring_diagram, dict) else {}

    # Build content string
    content = _build_content(
        vendor=vendor,
        product=product,
        part_number=part_number,
        component_type=component_type,
        ratings=clean_ratings,
        terminals=terminals,
        wiring_model=wiring_model,
    )

    # Build provenance
    provenance = [{
        "source": "telegram_photo" if "telegram" in str(photo_path).lower() else "photo_enrichment",
        "photo_id": photo_id or Path(photo_path).stem,
        "timestamp": datetime.now().isoformat(),
    }]

    return {
        "existing_atom_id": existing_atom_id,
        "conflict": conflict,
        "atom_type": "spec",
        "vendor": vendor,
        "product": product,
        "part_number": part_number,
        "component_type": component_type,
        "title": f"{vendor} {product}".strip() or f"{vendor} {part_number}".strip(),
        "summary": _build_summary(vendor, product, part_number, component_type, clean_ratings),
        "content": content[:5000],
        "keywords": keywords,
        "ratings": clean_ratings,
        "terminals": terminals,
        "wiring_model": wiring_model,
        "manual_refs": kb_manual_refs,
        "provenance": provenance,
        "needs_review": conflict,
    }


def _build_content(
    vendor: str,
    product: str,
    part_number: str,
    component_type: str,
    ratings: dict,
    terminals: dict,
    wiring_model: dict,
) -> str:
    """Build a human-readable content string from structured data."""
    parts = []

    if component_type:
        parts.append(f"Component Type: {component_type}")
    if vendor:
        parts.append(f"Vendor: {vendor}")
    if product:
        parts.append(f"Product: {product}")
    if part_number:
        parts.append(f"Part Number: {part_number}")

    if ratings:
        parts.append("")
        parts.append("Ratings:")
        for k, v in ratings.items():
            if v:
                parts.append(f"  {k.replace('_', ' ').title()}: {v}")

    if terminals:
        parts.append("")
        parts.append("Terminal Layout:")
        for tid, info in sorted(terminals.items()):
            label = info.get("label", "") if isinstance(info, dict) else str(info)
            parts.append(f"  Terminal {tid}: {label}")

    if wiring_model:
        parts.append("")
        parts.append("Wiring Model:")
        parts.append(json.dumps(wiring_model, indent=2))

    return "\n".join(parts)


def _build_summary(
    vendor: str,
    product: str,
    part_number: str,
    component_type: str,
    ratings: dict,
) -> str:
    """Build a short summary string."""
    parts = []
    if vendor:
        parts.append(vendor)
    if product:
        parts.append(product)
    elif part_number:
        parts.append(part_number)
    if component_type:
        parts.append(f"({component_type})")
    if ratings.get("current"):
        parts.append(f"{ratings['current']}")
    if ratings.get("voltage"):
        parts.append(f"{ratings['voltage']}")
    return " ".join(parts) if parts else "Unknown component"


# ---------------------------------------------------------------------------
# Stage 4: UPSERT — insert new or update existing atom
# ---------------------------------------------------------------------------

def _upsert_atom(atom_data: dict) -> Optional[int]:
    """Insert or update a KB atom via the KnowledgeConnector.

    Returns the atom_id (existing or new), or None on failure.
    """
    try:
        kb = _get_sync_kb()
        if not kb:
            log.warning("No sync KB connector available — skipping upsert")
            return None
        existing_id = atom_data.get("existing_atom_id")

        if existing_id:
            # Update existing atom
            conflict = atom_data.get("conflict", False)
            updates = {}
            if atom_data.get("summary"):
                updates["summary"] = atom_data["summary"]
            if atom_data.get("content"):
                updates["content"] = atom_data["content"]
            if atom_data.get("keywords"):
                updates["keywords"] = atom_data["keywords"]
            if atom_data.get("wiring_model"):
                updates["wiring_model"] = atom_data["wiring_model"]
            if atom_data.get("manual_refs"):
                updates["manual_refs"] = atom_data["manual_refs"]

            provenance = None
            if atom_data.get("provenance"):
                provenance = atom_data["provenance"][0]

            success = kb.update_atom(
                existing_id,
                updates,
                provenance=provenance,
                conflict=conflict,
            )
            if success:
                log.info("Updated KB atom %d (conflict=%s)", existing_id, conflict)
                return existing_id
            else:
                log.warning("KB update failed for atom %d", existing_id)
                return None
        else:
            # Insert new atom
            atom_id = kb.insert_atom(atom_data)
            if atom_id:
                log.info("Created KB atom %d: %s %s",
                         atom_id, atom_data.get("vendor"), atom_data.get("product"))
            return atom_id

    except ImportError:
        log.warning("KnowledgeConnector not available — KB enrichment requires VPS deployment")
        return None
    except Exception as e:
        log.error("KB upsert failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Main entry point: enrich_from_photo
# ---------------------------------------------------------------------------

def enrich_from_photo(
    photo_path: str,
    tags: Optional[str] = None,
    photo_id: Optional[str] = None,
    skip_upsert: bool = False,
) -> EnrichmentResult:
    """Run the full 4-stage enrichment pipeline on a component photo.

    Args:
        photo_path: Path to the photo file.
        tags: Optional hint about the component tag (e.g., "K1").
        photo_id: Optional unique ID for this photo (e.g., Telegram file_id).
        skip_upsert: If True, skip the DB write (dry-run mode).

    Returns:
        EnrichmentResult with extracted data and KB atom ID.
    """
    log.info("Starting enrichment pipeline for %s", photo_path)

    # Stage 1: INGEST — Vision OCR
    log.info("Stage 1: INGEST — running vision OCR")
    vision_data = _ingest_photo(photo_path, tags=tags)

    # Normalize: Gemini may return a list for multi-component photos
    if isinstance(vision_data, list):
        if vision_data:
            log.info("Vision returned %d components, enriching first", len(vision_data))
            vision_data = vision_data[0]
        else:
            vision_data = {}

    # Stage 2: AUGMENT — search KB
    log.info("Stage 2: AUGMENT — searching KB")
    kb_matches = _augment_from_kb(vision_data)

    # Stage 3: SYNTHESIZE — merge into canonical form
    log.info("Stage 3: SYNTHESIZE — building atom data")
    atom_data = _synthesize(vision_data, kb_matches, photo_path, photo_id=photo_id)

    # Stage 4: UPSERT — write to KB
    atom_id = None
    is_new = False
    was_updated = False

    if not skip_upsert:
        log.info("Stage 4: UPSERT — writing to KB")
        existing_id = atom_data.get("existing_atom_id")
        atom_id = _upsert_atom(atom_data)

        if atom_id and not existing_id:
            is_new = True
        elif atom_id and existing_id:
            was_updated = True
    else:
        log.info("Stage 4: UPSERT — skipped (dry-run)")

    # Build summary message
    vendor = atom_data.get("vendor", "")
    product = atom_data.get("product", "")
    part_number = atom_data.get("part_number", "")
    component_type = atom_data.get("component_type", "")
    n_terminals = len(atom_data.get("terminals", {}))

    if is_new:
        summary = (
            f"New component: {vendor} {product or part_number} "
            f"({component_type}). Added to KB with {n_terminals} terminals."
        )
    elif was_updated:
        if atom_data.get("needs_review"):
            summary = (
                f"Known component: {vendor} {product or part_number}. "
                f"Conflicting data detected — flagged for review."
            )
        else:
            summary = (
                f"Known component: {vendor} {product or part_number}. "
                f"Updated with new photo data."
            )
    else:
        summary = (
            f"Identified: {vendor} {product or part_number} "
            f"({component_type}, {n_terminals} terminals)."
        )

    log.info("Enrichment complete: %s", summary)

    return EnrichmentResult(
        atom_id=atom_id,
        vendor=vendor,
        product=product,
        part_number=part_number,
        component_type=component_type,
        is_new=is_new,
        was_updated=was_updated,
        needs_review=atom_data.get("needs_review", False),
        summary=summary,
        raw_vision=vision_data,
        raw_kb_matches=kb_matches,
        atom_data=atom_data,
    )


# ---------------------------------------------------------------------------
# Legacy: batch enrichment from a WiringProject
# ---------------------------------------------------------------------------

def can_create_atom(comp: ComponentRecord) -> bool:
    """Check if we have enough data to create a KB atom for this component."""
    return bool(
        comp.manufacturer
        and comp.part_number
        and comp.component_type
        and len(comp.terminals) >= 2
    )


def build_atom_data(comp: ComponentRecord) -> dict[str, Any]:
    """Build a KB atom dict from a ComponentRecord."""
    terminal_lines = []
    for tid, term in sorted(comp.terminals.items()):
        parts = [f"Terminal {tid}"]
        if term.label:
            parts.append(f"({term.label})")
        if term.connected_to:
            parts.append(f"-> {term.connected_to}")
        if term.wire_color:
            parts.append(f"[{term.wire_color}]")
        terminal_lines.append(" ".join(parts))

    content_parts = [
        f"Component: {comp.component_type}",
        f"Manufacturer: {comp.manufacturer}",
        f"Part Number: {comp.part_number}",
    ]
    if comp.voltage_rating:
        content_parts.append(f"Voltage Rating: {comp.voltage_rating}")
    if comp.current_rating:
        content_parts.append(f"Current Rating: {comp.current_rating}")
    if comp.description:
        content_parts.append(f"Description: {comp.description}")
    content_parts.append("")
    content_parts.append("Terminal Layout:")
    content_parts.extend(terminal_lines)

    keywords = list(filter(None, [
        comp.part_number,
        comp.manufacturer,
        comp.component_type,
        comp.description,
    ]))

    return {
        "atom_type": "spec",
        "vendor": comp.manufacturer,
        "product": comp.part_number,
        "title": f"{comp.manufacturer} {comp.part_number}",
        "summary": f"{comp.manufacturer} {comp.part_number} ({comp.component_type})",
        "content": "\n".join(content_parts),
        "keywords": keywords,
        "terminals": {
            tid: {"label": term.label, "connected_to": term.connected_to}
            for tid, term in comp.terminals.items()
        },
        "wiring_model": {},
        "ratings": {
            "voltage": comp.voltage_rating,
            "current": comp.current_rating,
        },
    }


def enrich_from_project(project: WiringProject) -> list[dict[str, Any]]:
    """Find all components without KB atoms and build atom data for them.

    Returns a list of atom dicts ready for insertion.
    """
    atoms = []
    for tag, comp in project.components.items():
        if comp.kb_atom_id is not None:
            continue
        if not can_create_atom(comp):
            continue
        atom = build_atom_data(comp)
        atom["source_tag"] = tag
        atom["source_project"] = project.project_id
        atoms.append(atom)
    return atoms


def insert_atom(atom_data: dict[str, Any]) -> Optional[int]:
    """Insert a KB atom into the knowledge_atoms table.

    Returns the new atom_id if successful, None otherwise.
    Legacy wrapper around _upsert_atom.
    """
    return _upsert_atom(atom_data)
