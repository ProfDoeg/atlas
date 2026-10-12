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
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
ELEMENT = {"Aries": "Fire", "Leo": "Fire", "Sagittarius": "Fire",
           "Taurus": "Earth", "Virgo": "Earth", "Capricorn": "Earth",
           "Gemini": "Air", "Libra": "Air", "Aquarius": "Air",
           "Cancer": "Water", "Scorpio": "Water", "Pisces": "Water"}
MODE = {"Aries": "Cardinal", "Cancer": "Cardinal", "Libra": "Cardinal", "Capricorn": "Cardinal",
        "Taurus": "Fixed", "Leo": "Fixed", "Scorpio": "Fixed", "Aquarius": "Fixed",
        "Gemini": "Mutable", "Virgo": "Mutable", "Sagittarius": "Mutable", "Pisces": "Mutable"}


def sign_name(lon):
    return SIGNS[int((lon % 360.0) // 30.0)]


def orb_for(b1, b2):
    return 8.0 if "sun" in (b1, b2) or "moon" in (b1, b2) else 6.0


def sep(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def sign_text(lon):
    lon = lon % 360.0
    i = int(lon // 30.0)
    d = lon - 30.0 * i
    dd = int(d)
    mm = int(round((d - dd) * 60))
    if mm == 60:
        dd, mm = dd + 1, 0
    return f"{SIGNS[i]} {dd}°{mm:02d}′"


def circular_mean(lons):
    """mean longitude (deg) as the angle of the mean unit vector -- the right way
    to average points on a circle; a plain arithmetic mean breaks across 0/360"""
    import math
    sx = sum(math.cos(math.radians(l)) for l in lons)
    sy = sum(math.sin(math.radians(l)) for l in lons)
    return math.degrees(math.atan2(sy, sx)) % 360.0


def classify_triad(seps):
    """seps: the three pairwise separations (deg) among three points. Returns a
    label if they match a recognized 3-point pattern within a loose 6 deg orb,
    else None."""
    orb = 6.0
    near = lambda a, b: abs(a - b) <= orb
    if all(near(s, 120) for s in seps):
        return "Grand Trine (all three ~120° apart)"
    if sum(1 for s in seps if near(s, 180)) == 1 and sum(1 for s in seps if near(s, 90)) == 2:
        return "T-square (two in opposition, the third square to both)"
    if all(near(s, 0) for s in seps):
        return "Stellium (all three conjunct)"
    if all(near(s, 60) for s in seps):
        return "all three in mutual sextile"
    return None


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

    if len(people) >= 2:
        from collections import Counter
        lines.append("## Sun-sign distribution\n")
        lines.append("| person | sun sign |")
        lines.append("|---|---|")
        for p in people:
            lines.append(f"| {p['traveler']} | {sign_name(p['bodies']['sun'])} |")
        lines.append("")
        sun_counts = Counter(sign_name(p["bodies"]["sun"]) for p in people)
        repeats = {s: n for s, n in sun_counts.items() if n > 1}
        if repeats:
            lines.append("Repeated: " + ", ".join(f"{s} x{n}" for s, n in repeats.items()) + "\n")

        lines.append("## Elements and modes (every body, every person pooled)\n")
        all_signs = [sign_name(lon) for p in people for lon in p["bodies"].values()]
        n_total = len(all_signs)
        el_counts = Counter(ELEMENT[s] for s in all_signs)
        mo_counts = Counter(MODE[s] for s in all_signs)
        lines.append(f"{n_total} body-placements pooled across {len(people)} people.\n")
        lines.append("| element | n | % |")
        lines.append("|---|---|---|")
        for el in ["Fire", "Earth", "Air", "Water"]:
            n = el_counts.get(el, 0)
            lines.append(f"| {el} | {n} | {100.0*n/n_total:.0f}% |")
        lines.append("")
        lines.append("| mode | n | % |")
        lines.append("|---|---|---|")
        for mo in ["Cardinal", "Fixed", "Mutable"]:
            n = mo_counts.get(mo, 0)
            lines.append(f"| {mo} | {n} | {100.0*n/n_total:.0f}% |")
        lines.append("")

        lines.append("## Composite chart (circular mean of the group)\n")
        lines.append("One synthetic body position per planet, averaged across everyone below "
                     "(circular mean, not a plain average, so it handles the 0/360 wrap) -- "
                     "reads as a single chart for the group as a unit.\n")
        lines.append("| body | composite position |")
        lines.append("|---|---|")
        common = [b for b in BODIES if all(b in p["bodies"] for p in people)]
        for b in common:
            m = circular_mean([p["bodies"][b] for p in people])
            lines.append(f"| {GLYPH.get(b,'')} {b} | {sign_text(m)} |")
        lines.append("")

    if len(people) == 3:
        lines.append("## Triad patterns (same body, all three people)\n")
        lines.append("For each body, the three pairwise separations among the three people's "
                     "placements, checked against known 3-point shapes (orb 6°).\n")
        found_any = False
        common = [b for b in BODIES if all(b in p["bodies"] for p in people)]
        for b in common:
            lons = [p["bodies"][b] for p in people]
            seps = [sep(lons[0], lons[1]), sep(lons[0], lons[2]), sep(lons[1], lons[2])]
            label = classify_triad(seps)
            if label:
                found_any = True
                lines.append(f"- {GLYPH.get(b,'')} {b}: {label} ({', '.join(f'{s:.1f}°' for s in seps)})")
        if not found_any:
            lines.append("- no recognized 3-point pattern on any shared body")
        lines.append("")

    out_path = ZODIAC / f"synastry_{group_name}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{group_name}: {len(people)} people, {len(excluded)} excluded, "
          f"{total_aspects} cross-person aspects -> {out_path}")


if __name__ == "__main__":
    main()
