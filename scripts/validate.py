"""Gate a fetched portfolio page before it replaces the published one.

This repo publishes a page it does not build. The build, its sources and its
parity tests live in phuazz/breadth-thrust-etf; all that happens here is a
scheduled fetch. That makes this the only place a silently-wrong page can be
stopped, so the fetch is not trusted on HTTP 200 alone.

Refusing to publish leaves the previous page up, which is the safe failure: a
day-old holdings table is a much smaller problem than a truncated, empty or
backwards one.

Usage:
    python scripts/validate.py <candidate.html> [<currently-published.html>]

Exit 0 to publish, 1 to keep what is already there.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# A truncated download is the failure this catches; the real page is ~33 KB.
MIN_BYTES = 12_000
MAX_BYTES = 2_000_000

START = "// __PORTFOLIO_DATA_START__"
END = "// __PORTFOLIO_DATA_END__"
PREFIX = "const PORTFOLIO_DATA_INLINE = "

# Disclosures are load-bearing on a page showing simulated performance to other
# people. If a rebuild ever drops them, this page must not carry it.
REQUIRED_TEXT = (
    "simulated",
    "no live track record",
    "not investment advice",
)

WEIGHT_TOLERANCE = 1e-6


class Rejected(RuntimeError):
    """The candidate must not be published."""


def extract_payload(html: str) -> dict:
    start, end = html.find(START), html.find(END)
    if start == -1 or end == -1 or end < start:
        raise Rejected("data markers missing or out of order — not a built page")
    block = html[start + len(START):end].strip()
    if not block.startswith(PREFIX) or not block.endswith(";"):
        raise Rejected("data block is not the expected inline assignment")
    body = block[len(PREFIX):-1]
    if body == "null":
        raise Rejected("page shipped with its data still null — the build did not inject")
    try:
        return json.loads(body.replace("<\\/", "</"))
    except json.JSONDecodeError as exc:
        raise Rejected(f"inlined data is not valid JSON: {exc}") from exc


def check_structure(html: str) -> None:
    n = len(html.encode("utf-8"))
    if not (MIN_BYTES <= n <= MAX_BYTES):
        raise Rejected(f"page is {n:,} bytes, outside {MIN_BYTES:,}-{MAX_BYTES:,}")
    if 'name="viewport"' not in html:
        raise Rejected("no viewport meta — would render unreadably on a phone")
    flat = " ".join(html.split()).lower()
    for phrase in REQUIRED_TEXT:
        if phrase not in flat:
            raise Rejected(f"required disclosure missing: {phrase!r}")
    for marker in ("<<<<<<<", ">>>>>>>"):
        if marker in html:
            raise Rejected(f"merge conflict marker {marker!r} in the page")


def check_payload(payload: dict) -> str:
    as_of = payload.get("as_of")
    if not as_of or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(as_of)):
        raise Rejected(f"as_of is missing or not a date: {as_of!r}")

    holdings = payload.get("holdings") or []
    if not holdings:
        raise Rejected("no holdings — an empty book is never correct here")

    total = sum(h.get("weight", 0) for h in holdings)
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise Rejected(f"holdings sum to {total:.8f}, not 1.0")

    sleeves = payload.get("sleeves") or []
    sleeve_total = sum(s.get("weight", 0) for s in sleeves)
    if not sleeves or abs(sleeve_total - 1.0) > WEIGHT_TOLERANCE:
        raise Rejected(f"sleeve split sums to {sleeve_total:.8f}, not 1.0")

    if any(not h.get("name") for h in holdings):
        raise Rejected("a holding has no fund name")

    curve = payload.get("curve") or {}
    dates, equity = curve.get("dates") or [], curve.get("equity") or []
    if len(dates) != len(equity) or not dates:
        raise Rejected("curve is empty or ragged")
    if dates[-1] != as_of:
        raise Rejected(f"curve ends {dates[-1]} but positions are as of {as_of}")
    if dates != sorted(dates):
        raise Rejected("curve dates are not in order")

    return str(as_of)


def check_not_going_backwards(new_as_of: str, published: Path | None) -> str:
    """The guard that a size or schema check cannot give you.

    A well-formed page carrying an OLDER as-of than the one already up means an
    upstream rollback, a stale cache, or a refresh that quietly republished old
    state. Every structural check above passes on it. Publishing it would walk
    the page backwards in time without anything looking wrong.
    """
    if published is None or not published.exists():
        return "first publish — nothing to compare against"
    try:
        old = extract_payload(published.read_text(encoding="utf-8"))
    except Rejected:
        # Whatever is up is unreadable; a valid candidate is an improvement.
        return "published page could not be parsed — publishing the candidate"
    old_as_of = str(old.get("as_of") or "")
    if not old_as_of:
        return "published page has no as_of — publishing the candidate"
    if new_as_of < old_as_of:
        raise Rejected(
            f"candidate is dated {new_as_of}, older than the published "
            f"{old_as_of} — refusing to walk the page backwards"
        )
    if new_as_of == old_as_of:
        return f"same as-of ({new_as_of}) — content may still differ"
    return f"as-of advances {old_as_of} -> {new_as_of}"


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    candidate = Path(argv[1])
    published = Path(argv[2]) if len(argv) == 3 else None

    html = candidate.read_text(encoding="utf-8")
    check_structure(html)
    payload = extract_payload(html)
    as_of = check_payload(payload)
    note = check_not_going_backwards(as_of, published)

    print(f"OK  {len(html.encode('utf-8')):,} bytes · {len(payload['holdings'])} "
          f"positions · as of {as_of}")
    print(f"    {note}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Rejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        print("Keeping the currently published page.", file=sys.stderr)
        raise SystemExit(1) from exc
