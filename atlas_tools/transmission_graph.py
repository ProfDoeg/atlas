#!/usr/bin/env python3
"""Person -> work -> person: the edges the atlas could not draw while it was a graph of people.

Anthony, 2026-10-17, on Hyperstition: "Do it."

The game's Circuit claims transmission through text across centuries, but connections.csv can only record that
when one person NAMES another (type T1, wrote_about). Two men four centuries apart who never met, both reading
the same book, are invisible to it. The works lists change that, and this builds the edges.

Two kinds, both traceable to one line of one works list, which is what the game's non-negotiable rule requires:

  shared_work  Two subjects' works lists carry the same title. Usually one made it and the other translated,
               edited or commented on it; sometimes co-authorship. Generic titles are dropped (see GENERIC):
               "Letters", "Opera omnia" and "Poems" would otherwise wire half the roster together.
  work_names   A work's title or description names another atlas subject. Ficino's Plato translations are an
               edge to Plato; Abulafia's commentary on Sefer Yetzirah is an edge to whoever else touches it.
               This is the richer kind, and it is directed: A made a thing about B.

Matching people by name is where this can go wrong, so it is deliberately strict. A name must be the subject's
filing surname, at least five characters, not a word that is also ordinary language, and capitalised where it
appears. Loose matching here would manufacture edges, and a manufactured edge in this game is worse than a
missing one -- the whole uncanny quality depends on every card being checkable.

    python3 atlas_tools/transmission_graph.py            # writes ~/corpus/transmission.csv and a summary
    python3 atlas_tools/transmission_graph.py --chain    # also reports where edges land on DESIGN.md's trunk
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ATLAS = Path(__file__).resolve().parent.parent
INVENTORY = Path(os.path.expanduser("~/corpus/inventory.jsonl"))
OUT = Path(os.path.expanduser("~/corpus/transmission.csv"))

# Titles too generic to be evidence of a shared work.
GENERIC = {"letters", "opera omnia", "poems", "works", "collected works", "sermons", "essays", "notebooks",
           "correspondence", "memoirs", "autobiography", "diary", "diaries", "lectures", "speeches",
           "complete works", "selected works", "writings", "fragments", "treatises", "commentaries",
           "opera", "obras completas", "obras", "cartas", "poesias", "sonnets", "songs", "untitled",
           "oeuvres completes", "oeuvres", "gesammelte schriften", "gesammelte werke", "werke",
           "collected papers", "collected essays", "selected letters", "collected poems"}

# Surnames that are also ordinary words, or too ambiguous to match on alone.
STOP_NAMES = {"bacon", "paul", "david", "solomon", "abraham", "moses", "jesus", "noah", "virgil", "king",
              "young", "black", "white", "price", "marsh", "bell", "ford", "cook", "fisher", "land",
              "church", "pope", "cross", "stone", "hunt", "baker", "carpenter", "mason", "miller"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_subjects():
    out = {}
    with open(ATLAS / "catalog_subjects.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["slug"]] = r["traveler"]
    return out


def name_index(subjects):
    """[(normalised full name, slug)], longest first. FULL names only.

    A first pass matched on the filing surname alone and the result was junk, at a rate that would have poisoned
    the game: "Jefferson" caught Geoffrey Jefferson and wired Turing to Thomas Jefferson; "North" caught North
    America and wired Warburg to Oliver North; "Alexander" caught Alexander of Aphrodisias; "Alberti" caught
    Albertus Magnus's own *Secreta Alberti* and wired him to Leon Battista Alberti. A surname is not an
    identifier, and no stop-list fixes that -- the failures are open-ended. So a match now requires the whole
    name, given and family, as a contiguous string. That loses real edges where a work names only the surname,
    and it is the right trade: a manufactured edge here is worse than a missing one, because the game's entire
    claim on the player is that any card can be turned over and checked.
    """
    out = []
    for slug, traveler in subjects.items():
        base = re.sub(r"\s*\(.*?\)\s*", " ", traveler).split(",")[0]
        n = norm(base)
        if len(n.split()) >= 2 and len(n) >= 9:
            out.append((n, slug))
        elif len(n.split()) == 1 and len(n) >= 7 and n not in STOP_NAMES:
            # Mononyms, admitted narrowly. Requiring two words excluded Ezekiel, Abulafia, Quintilian and
            # Simonides outright -- and Ezekiel is the one that matters, because Moses de Leon's works list
            # carries a "Commentary on the Vision of Ezekiel" that is precisely the edge DESIGN.md calls its
            # one conjectural splice. Seven characters and the stop-list keep out Paul, David and Solomon,
            # which are ordinary words as well as names.
            out.append((n, slug))
        else:
            continue
        # the parenthetical alias too, when it is itself a full name
        for alias in re.findall(r"\((.*?)\)", traveler):
            a = norm(alias.split(",")[0])
            if len(a.split()) >= 2 and len(a) >= 9:
                out.append((a, slug))
        # The slug itself, when it is a single token. The catalog's traveler string is a display name and often
        # longer than the name anyone writes: Ezekiel is filed with an epithet, so the mononym branch above
        # never fired for him -- and his is the one that matters, since Moses de Leon's "Commentary on the
        # Vision of Ezekiel" is the text DESIGN.md's conjectural splice is made of.
        if "_" not in slug and len(slug) >= 7 and slug not in STOP_NAMES:
            out.append((slug, slug))
    out.sort(key=lambda p: -len(p[0]))
    return out


def load_works():
    by_slug = defaultdict(list)
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            by_slug[r["slug"]].append(r)
    return by_slug


def main():
    subjects = load_subjects()
    names = name_index(subjects)
    works = load_works()
    edges = []

    # --- shared_work
    title_owners = defaultdict(set)
    title_row = {}
    for slug, rows in works.items():
        for r in rows:
            t = norm(r.get("title"))
            if not t or t in GENERIC or len(t) < 8:
                continue
            title_owners[t].add(slug)
            title_row.setdefault((t, slug), r)
    for t, owners in title_owners.items():
        if len(owners) < 2:
            continue
        owners = sorted(owners)
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = owners[i], owners[j]
                ra = title_row[(t, a)]
                edges.append({"subject_slug": a, "counterpart_slug": b, "kind": "shared_work",
                              "via_work": ra.get("title", ""), "year": ra.get("year") or "",
                              "evidence": (ra.get("date_text") or ra.get("kind") or "")[:200]})

    # --- work_names
    for slug, rows in works.items():
        for r in rows:
            blob = " ".join([str(r.get("title") or ""), str(r.get("note") or ""),
                             str(r.get("date_text") or "")])
            nblob = norm(blob)
            for full, other in names:
                if other == slug or full not in nblob:
                    continue
                edges.append({"subject_slug": slug, "counterpart_slug": other, "kind": "work_names",
                              "via_work": (r.get("title") or "")[:160], "year": r.get("year") or "",
                              "evidence": re.sub(r"\s+", " ", blob)[:240]})

    # dedupe on (subject, counterpart, via_work, kind)
    seen, uniq = set(), []
    for e in edges:
        k = (e["subject_slug"], e["counterpart_slug"], norm(e["via_work"]), e["kind"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["subject_slug", "counterpart_slug", "kind", "via_work",
                                           "year", "evidence"])
        w.writeheader()
        for e in uniq:
            w.writerow(e)

    kinds = defaultdict(int)
    pairs = set()
    people = set()
    for e in uniq:
        kinds[e["kind"]] += 1
        pairs.add(tuple(sorted((e["subject_slug"], e["counterpart_slug"]))))
        people.add(e["subject_slug"])
        people.add(e["counterpart_slug"])
    print(f"{len(uniq)} transmission edges over {len(pairs)} distinct pairs, {len(people)} people")
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<14} {n}")
    dated = [e for e in uniq if e["year"]]
    print(f"  dated           {len(dated)}")
    print(f"\nwrote {OUT}")

    if "--chain" in sys.argv:
        trunk = ["nabucodonosor_ii", "ezekiel", "moses_de_leon", "abraham_abulafia",
                 "giovanni_pico_della_mirandola", "solomon", "newton", "giordano_bruno", "ramon_llull",
                 "gottfried_wilhelm_leibniz", "johannes_trithemius", "john_dee", "adam_smith",
                 "cosimo_de_medici", "lorenzo_de_medici_il_magnifico", "nicholas_of_cusa"]
        print("\nedges touching DESIGN.md's trunk:")
        for e in uniq:
            if e["subject_slug"] in trunk or e["counterpart_slug"] in trunk:
                print("  %-26s %-26s %-12s %s"
                      % (e["subject_slug"][:26], e["counterpart_slug"][:26], e["kind"],
                         e["via_work"][:54]))


if __name__ == "__main__":
    main()
