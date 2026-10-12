#!/usr/bin/env python3
"""A cross-referenced slice of the atlas for one year: who was alive, what's dated
that year, and where multiple subjects' stops converge on the same place and date.

    python3 atlas_tools/year_slice.py 1888

Reads catalog_subjects.csv and catalog_stops.csv from the atlas repo root (this
script's parent directory). Writes a report to year_<N>_slice.md next to the CSVs
and prints a short summary to stdout.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SUBJECTS_CSV = REPO / "catalog_subjects.csv"
STOPS_CSV = REPO / "catalog_stops.csv"


def parse_year_span(years_field):
    """Best-effort birth-death span from the free-text 'years' column."""
    s = years_field.strip()
    bce = "BCE" in s.upper() or "A.C" in s.upper() or "a. C" in s
    nums = re.findall(r"\d{3,4}", s)
    if not nums:
        return None
    nums = [int(n) for n in nums]
    if bce:
        nums = [-n for n in nums]
    if len(nums) == 1:
        if s.rstrip().endswith("-"):
            return (nums[0], 2026)  # still living, per the atlas's own convention
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


def load(year):
    subjects = list(csv.DictReader(open(SUBJECTS_CSV, encoding="utf-8")))
    stops = list(csv.DictReader(open(STOPS_CSV, encoding="utf-8")))
    name_by_slug = {r["slug"]: r["traveler"] for r in subjects}

    alive = []
    for r in subjects:
        span = parse_year_span(r["years"])
        if span and span[0] <= year <= span[1]:
            alive.append((r["slug"], r["traveler"], r["years"]))
    alive.sort(key=lambda x: x[1])

    dated = defaultdict(list)
    for r in stops:
        y = stop_year(r["date"])
        if y == year:
            dated[r["slug"]].append((r["date"], r["stop_name"]))

    # convergence: two or more different subjects with a stop sharing the same
    # (rounded lat/lon, date) -- a cheap proxy for "same place, same moment"
    by_place_date = defaultdict(set)
    place_label = {}
    for r in stops:
        y = stop_year(r["date"])
        if y != year:
            continue
        try:
            key = (round(float(r["lat"]), 1), round(float(r["lng"]), 1), r["date"])
        except ValueError:
            continue
        by_place_date[key].add(r["slug"])
        place_label[key] = r["stop_name"]
    convergences = [
        (key, slugs) for key, slugs in by_place_date.items() if len(slugs) > 1
    ]
    convergences.sort(key=lambda kv: kv[0][2])

    return alive, dated, convergences, name_by_slug


def main():
    if len(sys.argv) != 2:
        print("usage: python3 year_slice.py <year>", file=sys.stderr)
        sys.exit(1)
    year = int(sys.argv[1])
    alive, dated, convergences, name_by_slug = load(year)

    out_path = REPO / f"year_{year}_slice.md"
    lines = [f"# Atlas slice: {year}\n"]
    lines.append(
        f"{len(alive)} subjects alive (birth-death span includes {year}); "
        f"{len(dated)} of them have at least one stop explicitly dated {year}.\n"
    )

    genuine = [(k, s) for k, s in convergences if not k[2].endswith("-01-01")]
    placeholder = [(k, s) for k, s in convergences if k[2].endswith("-01-01")]

    lines.append(f"## Convergences, specific date ({len(genuine)})\n")
    lines.append(
        "Two or more subjects with a stop at the same place (rounded to 0.1 deg) "
        "on the same specific date -- a cheap proxy, not a guarantee of a real "
        "crossing; verify before treating as a documented meeting.\n"
    )
    for (lat, lon, date), slugs in genuine:
        names = ", ".join(sorted(name_by_slug[s] for s in slugs))
        lines.append(f"- {date} ({lat}, {lon}): {names}")
    lines.append("")

    lines.append(f"## Convergences, Jan-1 PLACEHOLDER DATE ({len(placeholder)})\n")
    lines.append(
        f"CAVEAT: a stop dated exactly '-01-01' in this atlas usually means only "
        f"the year is attested and month/day were defaulted to 01 (check each "
        f"stop's date_confidence field) -- these are same-place-same-year, NOT "
        f"necessarily same-day. Do not present these as documented same-day "
        f"crossings without checking date_confidence first.\n"
    )
    for (lat, lon, date), slugs in placeholder:
        names = ", ".join(sorted(name_by_slug[s] for s in slugs))
        lines.append(f"- {date} ({lat}, {lon}): {names}")
    lines.append("")

    lines.append(f"## Dated stops in {year} ({sum(len(v) for v in dated.values())})\n")
    for slug in sorted(dated, key=lambda s: name_by_slug.get(s, s)):
        for date, stop_name in sorted(dated[slug]):
            lines.append(f"- {date} | {name_by_slug.get(slug, slug)} | {stop_name}")
    lines.append("")

    lines.append(f"## Alive in {year}, no dated stop that year ({len(alive) - len(dated)})\n")
    for slug, name, years in alive:
        if slug not in dated:
            lines.append(f"- {name} ({years})")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(alive)} alive in {year}; {len(dated)} with a dated stop; "
          f"{len(convergences)} convergence points")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
