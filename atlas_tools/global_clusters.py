#!/usr/bin/env python3
"""Same-place-and-date convergences across the WHOLE atlas, not one year --
the year_slice.py convergence check with the year filter removed. Also
reports the Sun-sign distribution across all subjects, since that's the
other sense of "cluster" in a dataset like this.

    python3 atlas_tools/global_clusters.py

Reads catalog_stops.csv and catalog_subjects.csv at the repo root. Writes
global_clusters.md next to them and prints a short summary.
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SUBJECTS_CSV = REPO / "catalog_subjects.csv"
STOPS_CSV = REPO / "catalog_stops.csv"
ZODIAC_CSV = REPO / "zodiac" / "_atlas_zodiac.csv"


def load():
    subjects = list(csv.DictReader(open(SUBJECTS_CSV, encoding="utf-8")))
    stops = list(csv.DictReader(open(STOPS_CSV, encoding="utf-8")))
    name_by_slug = {r["slug"]: r["traveler"] for r in subjects}

    by_place_date = defaultdict(set)
    for r in stops:
        date = r["date"].strip()
        if not date:
            continue
        try:
            key = (round(float(r["lat"]), 1), round(float(r["lng"]), 1), date)
        except ValueError:
            continue
        by_place_date[key].add(r["slug"])

    convergences = [(k, s) for k, s in by_place_date.items() if len(s) > 1]
    convergences.sort(key=lambda kv: -len(kv[1]))
    return convergences, name_by_slug


def sun_sign_distribution():
    if not ZODIAC_CSV.exists():
        return None
    rows = list(csv.DictReader(open(ZODIAC_CSV, encoding="utf-8")))
    # month/year-precision births default the day to Jan 1 and the Sun sign at
    # that precision is explicitly unreliable (atlas convention) -- Capricorn
    # would swamp the real distribution if those were counted
    day_rows = [r for r in rows if r.get("precision") == "day" and r.get("sun_sign")]
    return Counter(r["sun_sign"] for r in day_rows), len(day_rows)


def main():
    convergences, name_by_slug = load()
    genuine = [(k, s) for k, s in convergences if not k[2].endswith("-01-01")]
    placeholder = [(k, s) for k, s in convergences if k[2].endswith("-01-01")]

    lines = ["# Atlas-wide clusters\n"]
    lines.append(f"{len(convergences)} place+date points shared by 2+ subjects "
                 f"({len(genuine)} on a specific date, {len(placeholder)} only "
                 f"sharing the Jan-1 year-only placeholder date).\n")

    lines.append(f"## Specific-date convergences, largest first ({len(genuine)})\n")
    lines.append("Same rounded coordinate (0.1 deg) and the same explicit date, "
                 "across the whole atlas, any year. A proxy, not a documented "
                 "meeting -- verify before treating as a real crossing.\n")
    for (lat, lon, date), slugs in genuine:
        names = ", ".join(sorted(name_by_slug.get(s, s) for s in slugs))
        lines.append(f"- {date} ({lat}, {lon}), {len(slugs)}: {names}")
    lines.append("")

    lines.append(f"## Jan-1-placeholder convergences, largest first ({len(placeholder)})\n")
    lines.append("CAVEAT: '-01-01' here usually means only the year is attested; "
                 "same place and year, not necessarily the same day.\n")
    for (lat, lon, date), slugs in sorted(placeholder, key=lambda kv: -len(kv[1])):
        names = ", ".join(sorted(name_by_slug.get(s, s) for s in slugs))
        lines.append(f"- {date} ({lat}, {lon}), {len(slugs)}: {names}")
    lines.append("")

    dist = sun_sign_distribution()
    if dist:
        counts, total = dist
        lines.append(f"## Sun-sign distribution across all subjects ({total} day-precise births)\n")
        for sign, n in counts.most_common():
            lines.append(f"- {sign}: {n} ({100.0 * n / total:.1f}%)")
        lines.append("")

    out_path = REPO / "global_clusters.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(convergences)} place+date convergences ({len(genuine)} specific-date, "
          f"{len(placeholder)} Jan-1 placeholder); wrote {out_path}")
    if dist:
        counts, total = dist
        top = counts.most_common(3)
        print("top Sun signs:", ", ".join(f"{s} {n}" for s, n in top), f"of {total}")


if __name__ == "__main__":
    main()
