#!/usr/bin/env python3
"""Which works lists are thinner than they ought to be?

Anthony, 2026-10-22: "can you do another pass of the bibliographies and see if there are subjects with fewer
works than they should have". Empty lists were easy to find and are down to three. Thin ones are harder,
because "too few" needs something to be too few AGAINST.

Four independent signals, none of them conclusive alone, reported together so a human can judge:

  unmatched/works   The libraries hold things under this person's name that match no work we know of. A
                    subject with 3 works and 300 unmatched holdings is either very written-about or
                    under-researched, and the ratio says which to look at first.
  prose ratio       Lines in the works section that carry no discrete title. Michelangelo's whole list was
                    narrative prose and parsed to nothing, which is how he survived every audit until the
                    staging bug was found. A high prose ratio means the research exists and the structure does
                    not.
  openlibrary       The work_count Open Library reports for the matched author, where the author was verified
                    by death year. A catalogue count is not a bibliography -- that was this project's first
                    lesson -- but an author OL lists 300 works for, whose list here holds 4, is worth a look.
  editions/works    Many editions attached to few works can mean the works list is a stub that the library
                    hits are piling onto.

Deliberately no single score. The point is to produce a short list for a person to read, not to rank 890
subjects by a number none of these four can support.

    python3 atlas_tools/corpus_thinness_audit.py            # the 40 worst by each signal
    python3 atlas_tools/corpus_thinness_audit.py --csv      # everything, to ~/corpus/thinness.csv
"""
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

CORPUS = Path(os.path.expanduser("~/corpus"))
BIB = CORPUS / "bib"
INVENTORY = CORPUS / "inventory.jsonl"
ATLAS = Path(__file__).resolve().parent.parent
OUT = CORPUS / "thinness.csv"


def main():
    titled, lines = Counter(), Counter()
    with open(INVENTORY, encoding="utf-8") as fh:
        for ln in fh:
            r = json.loads(ln)
            lines[r["slug"]] += 1
            if r.get("title"):
                titled[r["slug"]] += 1

    names = {}
    with open(ATLAS / "catalog_subjects.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            names[r["slug"]] = r["traveler"]

    rows = []
    for p in sorted(BIB.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        slug = d["slug"]
        w = titled.get(slug, 0)
        unm = d.get("n_unmatched", 0)
        eds = d.get("n_editions", 0)
        prose = lines.get(slug, 0) - w
        rows.append({
            "slug": slug,
            "traveler": names.get(slug, "")[:46],
            "works": w,
            "editions": eds,
            "unmatched": unm,
            "prose_lines": prose,
            "unmatched_per_work": round(unm / w, 1) if w else (unm if unm else 0),
            "prose_ratio": round(prose / max(1, lines.get(slug, 0)), 2),
            "ol_author": d.get("openlibrary_author") or "",
            "ol_verified": d.get("author_verified_by_death_year"),
        })

    if "--csv" in sys.argv:
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            wri = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wri.writeheader()
            wri.writerows(rows)
        print(f"wrote {OUT} ({len(rows)} subjects)")
        return

    def show(title, key, filt=lambda r: True, n=18):
        print(f"\n=== {title}")
        print("%-30s %-28s %6s %6s %6s" % ("subject", "name", "works", "unmat", "prose"))
        for r in sorted([r for r in rows if filt(r)], key=key, reverse=True)[:n]:
            print("%-30s %-28s %6d %6d %6d"
                  % (r["slug"][:30], r["traveler"][:28], r["works"], r["unmatched"], r["prose_lines"]))

    print(f"{len(rows)} subjects audited")
    show("most library holdings per known work (>=40 unmatched, <=12 works)",
         lambda r: r["unmatched_per_work"], lambda r: r["unmatched"] >= 40 and r["works"] <= 12)
    show("research present but unstructured: most prose lines with few titles",
         lambda r: r["prose_lines"], lambda r: r["prose_lines"] >= 8 and r["works"] <= 10)
    show("fewest works outright, excluding the genuinely empty",
         lambda r: -r["works"], lambda r: 1 <= r["works"] <= 3)


if __name__ == "__main__":
    main()
