#!/usr/bin/env python3
"""The crossing table: where an essay crosses a life, and at which stop.

Anthony, 2026-10-25, having read both agents' answers: "Yes build it."

nodus2's structural reading, which is the reason this file exists. An ESSAY is one pass that crosses many lives
once each -- essay 219 touches ESMA, Penelope, Joan, the Vates embroidery, Novalis, Khorramdel. A JOURNEY is one
life's whole line, 25-45 dated stops. Weft and warp. Where a pass crosses a thread there is a knot, and the knot
is a STOP: a dated place carrying a quotation and a source. That is why stops carry quotations, a feature of the
data nobody designed for this reason.

Before this file the two layers did not touch. catalog_stops.csv has 37,944 stops and no essay column, and the
research pipeline's interlock rule deliberately refuses shared place or time as grounds for a link, so essay
resonance was not even an admissible relation. Without a crossing table the weave is an image; with one it is a
form, and the subjects no essay crosses are visibly warp with no weft through them.

WHAT COUNTS AS A CROSSING. The first version of this file reused transmission_graph.name_index() unchanged,
which demands a contiguous full name. That rule exists because matching a bare surname inside a WORK TITLE
poisoned the transmission graph: "Jefferson" caught Geoffrey Jefferson and wired Turing to Thomas Jefferson.
Applied to essays it failed in the opposite direction. Essay 182 is titled "goethe at volcano", names Goethe
fifteen times, and produced no crossing to him at all, because the atlas files him as "Johann Wolfgang von
Goethe" and prose says "Goethe". Across the corpus the strict rule found 194 crossings where nodus2 estimated
one to two thousand.

The diagnosis is that LENGTH was never the real safeguard -- AMBIGUITY was. A surname inside a title string is
dangerous because the title may belong to someone else entirely. A surname in an essay written by one author
about these very figures is almost always the figure, and the one real hazard is two subjects sharing it. So a
surname is admitted here when it is UNAMBIGUOUS ACROSS THE WHOLE ROSTER -- exactly one of the 890 carries it --
and refused when two or more do, which is the Hamilton, Maxwell and Jung case, where only the full name will
serve. Ordinary words that happen to be surnames stay excluded by transmission_graph's stop-list.

Every row records HOW it matched, "full" or "surname", so the weaker grade stays visible and the table can be
re-cut at the stricter standard without being rebuilt.

TWO GRADES, kept apart rather than blended:

  subject   The essay names the person. One row per essay-subject pair, with the matched form, the count, and
            the first sentence it appears in, so a reader can see the crossing rather than trust it.
  knot      The essay names the person AND a place that is one of that person's own stops. This is the
            crossing located: essay, life, place, date. These are the rows a printed edition could set.

The essays are bilingual in one file, English then Spanish, so a name is found twice by construction; matches
are deduplicated per essay and the mention count reports both halves together.

    python3 atlas_tools/crossing_table.py
    python3 atlas_tools/crossing_table.py --essay 219
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transmission_graph as TG  # noqa: E402  -- name_index, norm, load_subjects

ESSAYS = Path(os.path.expanduser("~/essays"))
ATLAS = Path(os.path.expanduser("~/taller/atlas"))
OUT = Path(os.path.expanduser("~/corpus/crossings.csv"))
OUT_KNOTS = Path(os.path.expanduser("~/corpus/crossings_knots.csv"))

# Stop names are "Place, the event" by house rule, so the place is the part before the first comma. Place words
# this generic would knot an essay to any life that passed through a continent.
PLACE_STOP = {"paris", "london", "rome", "madrid", "berlin", "vienna", "moscow", "cairo", "athens", "york",
              "america", "europe", "africa", "asia", "england", "france", "spain", "italy", "germany",
              "russia", "egypt", "greece", "china", "india", "japan", "israel", "palestine", "poland",
              "the city", "the sea", "the desert", "the river", "the mountain", "home", "exile", "prison",
              "the court", "the palace", "the temple", "the cathedral", "the university", "the academy"}
MIN_PLACE = 5


def strip_accents(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def fold(s):
    """Lowercase, accent-stripped, punctuation flattened -- the form names are matched in."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def essay_files():
    out = []
    for p in sorted(ESSAYS.glob("*.md")):
        m = re.match(r"^(\d+)_(.*)\.md$", p.name)
        if m:
            out.append((int(m.group(1)), m.group(2).replace("_", " "), p))
    return out


def sentences(text):
    """Rough sentence split, good enough to quote the crossing back to a reader."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\n+", text) if s.strip()]


def stops_by_slug():
    out = defaultdict(list)
    with open(ATLAS / "catalog_stops.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["slug"]].append(r)
    return out


def place_of(stop_name):
    """The place half of "Place, the event"."""
    return (stop_name or "").split(",")[0].strip()


def surname_index(subjects):
    """[(surname, slug)] for surnames exactly ONE subject in the roster carries.

    The ambiguous ones are dropped rather than guessed, which is the standing rule for this atlas: Hamilton,
    Maxwell and Jung are each worn by more than one subject, so those require the full name and are absent
    here. A surname is also refused when it is an ordinary word, using transmission_graph's own stop-list.
    """
    owners = defaultdict(set)
    for slug, traveler in subjects.items():
        base = re.sub(r"\s*\(.*?\)\s*", " ", traveler).split(",")[0]
        # "X of Y" is a given name plus a PLACE, not a family name. Taking the last token made "assisi" the
        # surname of Saint Francis, so any essay naming the town crossed him -- a false mechanism that happened
        # to give the right answer in essay 182 and would not elsewhere. Reducing to the first token is no
        # better: "Francis" alone would catch Francis Bacon. These subjects require their full name, which
        # name_index already carries, so nothing is lost.
        if re.search(r"\bof\b|\bde\b(?=\s)", fold(base)) and " " in fold(base):
            continue
        toks = [t for t in fold(base).split() if len(t) > 1]
        # Particles are not surnames: "von Goethe" -> goethe, "de Leon" -> leon, "ibn Arabi" -> arabi.
        while len(toks) > 1 and toks[-2] in ("von", "van", "de", "del", "della", "di", "da", "du", "la",
                                             "le", "el", "al", "ibn", "bin", "ben", "ter", "ten"):
            toks = toks[:-2] + [toks[-1]]
        if not toks:
            continue
        sur = toks[-1]
        if len(sur) < 5 or sur in TG.STOP_NAMES:
            continue
        owners[sur].add(slug)
    return [(sur, next(iter(slugs))) for sur, slugs in owners.items() if len(slugs) == 1]


def main():
    only = None
    if "--essay" in sys.argv:
        only = int(sys.argv[sys.argv.index("--essay") + 1])

    subjects = TG.load_subjects()
    # name_index returns transmission_graph's own normalisation; re-fold through this file's matcher so the
    # accented Spanish half of every essay is searched on the same footing as the English half.
    index = [(fold(n), slug, "full") for n, slug in TG.name_index(subjects)]
    index += [(sur, slug, "surname") for sur, slug in surname_index(subjects)]
    # The honorific short form. The atlas files him as "Francis of Assisi"; essay 182 writes "Saint Francis",
    # and a contiguous match on the filed name finds neither. Refusing the toponym as a surname was right and
    # cost this crossing until the short form was indexed too -- two words at least, so "Francis" alone, which
    # would catch Francis Bacon, is still refused.
    for slug, traveler in subjects.items():
        base = re.sub(r"\s*\(.*?\)\s*", " ", traveler).split(",")[0]
        short = re.split(r"\bof\b", fold(base))[0].strip()
        if short and short != fold(base) and len(short.split()) >= 2 and len(short) >= 9:
            index.append((short, slug, "full"))
        for honorific in ("saint", "san", "santa", "st"):
            cand = fold(f"{honorific} {short}") if short else ""
            if cand and len(short.split()) == 1 and len(short) >= 5:
                index.append((cand, slug, "full"))
    index = [(n, s, g) for n, s, g in index if n]
    # Longest first, and full names before surnames at equal length, so a subject is credited by its
    # strongest available match rather than whichever the dictionary happened to reach first.
    index.sort(key=lambda p: (-len(p[0]), p[2] != "full"))

    stops = stops_by_slug()
    rows, knots = [], []
    crossed = set()

    for num, title, path in essay_files():
        if only is not None and num != only:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        hay = fold(raw)
        sents = sentences(raw)
        folded_sents = [fold(s) for s in sents]

        seen = {}
        for name, slug, grade in index:
            if slug in seen:
                continue
            # Word-boundary match, so "abraham" does not fire inside "abrahamic".
            pat = r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])"
            if not re.search(pat, hay):
                continue
            n = len(re.findall(pat, hay))
            ctx = ""
            for s, fs in zip(sents, folded_sents):
                if re.search(pat, fs):
                    ctx = re.sub(r"\s+", " ", s)[:300]
                    break
            seen[slug] = (name, n, ctx, grade)

        for slug, (name, n, ctx, grade) in sorted(seen.items()):
            crossed.add(slug)
            rows.append({"essay": num, "essay_title": title, "slug": slug,
                         "traveler": subjects.get(slug, ""), "matched_as": name,
                         "match": grade, "mentions": n, "context": ctx})
            # Locate the knot: a place of this subject's own that the essay also names.
            for st in stops.get(slug, []):
                pl = place_of(st["stop_name"])
                f = fold(pl)
                if len(f) < MIN_PLACE or f in PLACE_STOP:
                    continue
                if re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])", hay):
                    knots.append({"essay": num, "essay_title": title, "slug": slug,
                                  "traveler": subjects.get(slug, ""), "place": pl,
                                  "stop_name": st["stop_name"], "date": st["date"],
                                  "date_confidence": st["date_confidence"],
                                  "segment": st["segment"], "stop_index": st["stop_index"],
                                  "lat": st["lat"], "lng": st["lng"]})

    if only is not None:
        for r in rows:
            print(f"  {r['slug']:<30} x{r['mentions']:<3} {r['match']:<8} as {r['matched_as']!r}")
            if r["context"]:
                print(f"      {r['context'][:150]}")
        print(f"\n{len(rows)} subjects crossed, {len(knots)} located to a stop")
        for k in knots:
            print(f"  KNOT {k['slug']:<24} {k['place'][:28]:<28} {k['date']}")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["essay", "essay_title", "slug", "traveler",
                                           "matched_as", "match", "mentions", "context"])
        w.writeheader()
        w.writerows(rows)
    with open(OUT_KNOTS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["essay", "essay_title", "slug", "traveler", "place", "stop_name",
                                           "date", "date_confidence", "segment", "stop_index", "lat", "lng"])
        w.writeheader()
        w.writerows(knots)

    per_essay = defaultdict(int)
    for r in rows:
        per_essay[r["essay"]] += 1
    n_essays = len({r["essay"] for r in rows})
    print(f"{len(rows)} crossings over {n_essays} essays and {len(crossed)} of {len(subjects)} subjects")
    print(f"{len(knots)} of those located to a named stop -- an essay, a life, a place and a date")
    print(f"\nsubjects no essay crosses: {len(subjects) - len(crossed)}"
          "   (warp with no weft through it)")
    if per_essay:
        hi = sorted(per_essay.items(), key=lambda kv: -kv[1])
        print(f"\nessays crossing the most lives:")
        for num, k in hi[:10]:
            print(f"  {num}  {k:>4} lives")
        print(f"  median {sorted(per_essay.values())[len(per_essay)//2]} lives per essay")
    print(f"\nwrote {OUT}\n      {OUT_KNOTS}")


if __name__ == "__main__":
    main()
