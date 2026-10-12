#!/usr/bin/env python3
"""Flag stops dated outside their own subject's birth-death span.

Started from two hand-found cases (Hegel in 1841, ten years dead; Fred Rogers
in 1790, 138 years unborn) that turned out, on inspection, to both be
INTENTIONAL: Hegel's is segment "The Afterlife of the System" (Schelling's
real 1841 Berlin lectures against Hegelianism); Rogers's borrows Schelling's
real 1790 Tubingen pin for a thematic essay link, not a travel claim. The
atlas deliberately narrates, as dated stops: (a) legacy/burial/reception
after death, (b) ancestry/family background before birth, and (c) thematic
pin-borrowing across subjects. A mechanical date-fence can't tell those
apart from a genuine typo -- this script narrows the net (tighter year
parsing, skips ambiguous "c./after/disputed" spans, drops segments whose
name reads as legacy/afterlife) but what's left still needs eyes, not a
verdict.

    python3 atlas_tools/lifespan_audit.py

Reads catalog_subjects.csv (years span) and catalog_stops.csv (dated stops)
at the repo root. Writes lifespan_audit.md and prints a short summary.
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SUBJECTS_CSV = REPO / "catalog_subjects.csv"
STOPS_CSV = REPO / "catalog_stops.csv"


AMBIGUOUS = re.compile(r"\bc\.|after |before |disputed|\?|fl\.|floruit", re.I)
LEGACY_SEGMENT = re.compile(r"afterlife|legacy|the grave|the ashes|posthum|after his|after her| burial|estate",
                            re.I)


def parse_year_span(years_field):
    """birth-death span from the free-text 'years' column; None if the field is
    too hedged (c., after, disputed, ...) to audit mechanically"""
    s = years_field.strip()
    if AMBIGUOUS.search(s):
        return None
    bce = bool(re.search(r"\bBCE?\b", s.upper())) or "A.C" in s.upper() or "a. C" in s
    nums = re.findall(r"\d{1,4}", s)  # 1-4 digits: catches 1st/2nd-century CE years too
    if not nums:
        return None
    nums = [int(n) for n in nums]
    if bce:
        nums = [-n for n in nums]
    if len(nums) == 1:
        if s.rstrip().endswith("-"):
            return (nums[0], 2026)
        return (nums[0], nums[0])
    return (min(nums), max(nums))


def stop_year(date_field):
    d = date_field.strip()
    if not d:
        return None
    neg = d.startswith("-")
    body = d[1:] if neg else d
    try:
        y = int(body[:4])
    except ValueError:
        return None
    return -y if neg else y


def main():
    subjects = list(csv.DictReader(open(SUBJECTS_CSV, encoding="utf-8")))
    stops = list(csv.DictReader(open(STOPS_CSV, encoding="utf-8")))
    span_by_slug = {r["slug"]: parse_year_span(r["years"]) for r in subjects}
    name_by_slug = {r["slug"]: r["traveler"] for r in subjects}

    before_birth, after_death, no_span, legacy_skipped = [], [], 0, 0
    for r in stops:
        span = span_by_slug.get(r["slug"])
        if span is None:
            no_span += 1
            continue
        y = stop_year(r["date"])
        if y is None:
            continue
        birth, death = span
        if y < birth:
            before_birth.append((r["slug"], r["date"], y, birth, death, r["segment"], r["stop_name"]))
        elif y > death:
            if LEGACY_SEGMENT.search(r["segment"]):
                legacy_skipped += 1
                continue
            after_death.append((r["slug"], r["date"], y, birth, death, r["segment"], r["stop_name"]))

    before_birth.sort(key=lambda t: t[3] - t[2], reverse=True)
    after_death.sort(key=lambda t: t[2] - t[4], reverse=True)

    lines = ["# Lifespan audit: stops dated outside their subject's own birth-death span\n"]
    lines.append(f"{len(before_birth)} stop(s) dated before birth, {len(after_death)} dated after "
                 f"death (plus {legacy_skipped} more after-death stops already excluded as "
                 f"legacy/afterlife-labeled segments), out of {len(stops)} total stops "
                 f"({no_span} subjects skipped: no parseable or too-hedged years span).\n")
    lines.append("Caveat, confirmed by hand on the two cases that started this script: most "
                 "'before birth' stops are deliberate ancestry/family-background narration, and "
                 "most remaining 'after death' stops are deliberate legacy/reception narration "
                 "that just didn't happen to use one of the segment-name keywords this script "
                 "filters on, or a thematic pin borrowed from another subject's real stop. This "
                 "list is a set of candidates to read by eye, not a bug list.\n")

    lines.append(f"## Dated before birth, worst first ({len(before_birth)})\n")
    lines.append("| slug | stop date | stop year | birth | death | gap | segment | stop |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for slug, date, y, birth, death, segment, stop_name in before_birth:
        lines.append(f"| {name_by_slug.get(slug, slug)} | {date} | {y} | {birth} | {death} "
                     f"| {birth - y} yr early | {segment} | {stop_name} |")
    lines.append("")

    lines.append(f"## Dated after death, worst first ({len(after_death)})\n")
    lines.append("| slug | stop date | stop year | birth | death | gap | segment | stop |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for slug, date, y, birth, death, segment, stop_name in after_death:
        lines.append(f"| {name_by_slug.get(slug, slug)} | {date} | {y} | {birth} | {death} "
                     f"| {y - death} yr late | {segment} | {stop_name} |")
    lines.append("")

    out_path = REPO / "lifespan_audit.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(before_birth)} before-birth, {len(after_death)} after-death, "
          f"{no_span} subjects skipped (no parseable span); wrote {out_path}")
    if before_birth:
        worst = before_birth[0]
        print(f"worst before-birth: {name_by_slug.get(worst[0])}, {worst[1]} ({worst[3]-worst[2]} yr early)")
    if after_death:
        worst = after_death[0]
        print(f"worst after-death: {name_by_slug.get(worst[0])}, {worst[1]} ({worst[2]-worst[4]} yr late)")


if __name__ == "__main__":
    main()
