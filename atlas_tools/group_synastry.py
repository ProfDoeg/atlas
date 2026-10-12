#!/usr/bin/env python3
"""Cross-person aspects (synastry) within a named group of atlas subjects: every
body of person A against every body of person B, within orb, for each pair in
the group. Built to look at the 1888 same-place clusters (Barcelona, Buenos
Aires, Paris, London, Vienna) the year-slice tool surfaced.

    python3 atlas_tools/group_synastry.py <name> <slug> <slug> ...

Reads zodiac/<slug>.zodiac.json (birth block; built by zodiac_readings.py).
Skips bodies/people whose only birth precision is "year" (the Sun reading is
explicitly flagged unreliable at that precision -- not usable for aspects).
Writes a report to zodiac/synastry_<name>.md and prints a short summary.
"""
import itertools
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ZODIAC = REPO / "zodiac"
SUBJECTS_CSV = REPO / "catalog_subjects.csv"

BODIES = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
GLYPH = {"sun": "☉", "moon": "☽", "mercury": "☿", "venus": "♀",
         "mars": "♂", "jupiter": "♃", "saturn": "♄"}
ASPECTS = [(0, "conjunction"), (60, "sextile"), (90, "square"), (120, "trine"), (180, "opposition")]


def orb_for(b1, b2):
    return 8.0 if "sun" in (b1, b2) or "moon" in (b1, b2) else 6.0


def sep(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def names():
    import csv
    return {r["slug"]: r["traveler"] for r in csv.DictReader(open(SUBJECTS_CSV, encoding="utf-8"))}


def load_person(slug):
    path = ZODIAC / f"{slug}.zodiac.json"
    if not path.exists():
        return None, f"no zodiac file for {slug}"
    d = json.loads(path.read_text(encoding="utf-8"))
    b = d.get("birth", {})
    if b.get("precision") != "day":
        return None, (f"{d.get('traveler', slug)}: birth precision is "
                       f"'{b.get('precision')}', not 'day' -- Sun sign at that "
                       f"precision is flagged unreliable, excluded from synastry")
    bodies = {k: b[k]["longitude"] for k in BODIES if k in b}
    return {"slug": slug, "traveler": d.get("traveler", slug), "date": b.get("date"), "bodies": bodies}, None


def pair_aspects(p1, p2):
    out = []
    for b1, lon1 in p1["bodies"].items():
        for b2, lon2 in p2["bodies"].items():
            s = sep(lon1, lon2)
            for angle, aname in ASPECTS:
                orb = orb_for(b1, b2)
                if abs(s - angle) <= orb:
                    out.append((abs(s - angle), b1, b2, aname, s))
    out.sort(key=lambda t: t[0])
    return out


def main():
    if len(sys.argv) < 3:
        print("usage: python3 group_synastry.py <name> <slug> <slug> ...", file=sys.stderr)
        sys.exit(1)
    group_name = sys.argv[1]
    slugs = sys.argv[2:]

    people, excluded = [], []
    for s in slugs:
        p, err = load_person(s)
        if p:
            people.append(p)
        else:
            excluded.append(err)

    lines = [f"# Synastry: {group_name}\n"]
    lines.append(f"{len(people)} usable chart(s), {len(excluded)} excluded.\n")
    if excluded:
        lines.append("## Excluded\n")
        for e in excluded:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## People\n")
    for p in people:
        lines.append(f"- {p['traveler']} (b. {p['date']})")
    lines.append("")

    total_aspects = 0
    for p1, p2 in itertools.combinations(people, 2):
        aspects = pair_aspects(p1, p2)
        lines.append(f"## {p1['traveler']} <-> {p2['traveler']}\n")
        if not aspects:
            lines.append("No aspect within orb.\n")
            continue
        lines.append("| orb | body | aspect | body | separation |")
        lines.append("|---|---|---|---|---|")
        for orb, b1, b2, aname, s in aspects:
            lines.append(f"| {orb:.2f}° | {GLYPH.get(b1,'')} {p1['traveler'].split()[0]} {b1} "
                         f"| {aname} | {GLYPH.get(b2,'')} {p2['traveler'].split()[0]} {b2} | {s:.2f}° |")
        lines.append("")
        total_aspects += len(aspects)

    out_path = ZODIAC / f"synastry_{group_name}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{group_name}: {len(people)} people, {len(excluded)} excluded, "
          f"{total_aspects} cross-person aspects -> {out_path}")


if __name__ == "__main__":
    main()
