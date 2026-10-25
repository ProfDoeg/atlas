#!/usr/bin/env python3
"""Move modern research papers out from under people who died before modern research publishing existed.

Anthony's rule for the corpus is the whole reason this exists: "If we allow every book ABOUT a person it wil
blow up the project. Works BY the person." The Archive's creator search obeys the name it is given, and a name
is not a person. Emir Abdelkader (d. 1883) acquired 105 papers on nonlinear control and oncology, because
"Abdelkader" is a common Arabic name among living researchers. "Guinevere" acquired 125 astrophysics preprints.
Rabia al-Adawiyya, who died in 801, acquired a 2025 paper on sentiment analysis. Saint Clotilde, d. 545,
acquired exosome physiology. Newton has neutron-star symmetry energy; Michelangelo has electron
interferometry; Dante has Hubble proper motions; Schiller has percutaneous angioplasty.

WHY THE OBVIOUS RULES ARE ALL WRONG, because each was tried and rejected against the data:

  one-token name match      Would destroy Herodotus, Plato, Aristotle and Moses. A mononym is the correct and
                            complete filing name for the people who have one.
  printed long after death  Would destroy Dante's 1921 Divina commedia, Newton's 1846 Principia and
                            Leonardo's Trattato della pittura. A posthumous edition is the normal case for
                            everyone in this atlas.
  in a paper collection     Would destroy EULER'S OWN PAPERS. Someone has translated Euler into English and
                            posted him to arXiv: "De seriebus divergentibus", "Observations on a certain
                            theorem of Fermat". All genuinely his.
  unmatched by the
  bibliography              Would destroy 24,887 files, about seventy per cent of the corpus. Cicero's
                            unmatched holdings are Cicero -- "Tvscvlanarvm Quaestionvm", his letters to
                            Atticus, De natura deorum in Catalan. The matcher refuses cross-language and
                            variant-spelling matches by design, so "unmatched" means "a human should look",
                            which is what corpus/unmatched is for. Promoting that queue to a verdict is the
                            same mistake as every other stale-decision bug in this corpus.

SO THE TEST IS A CONJUNCTION, and each clause is there to exclude one of the above:

  1. the subject died before 1900                      -- they cannot be a living co-author
  2. the item is in a research-paper collection        -- arxiv, pubmed, biostor and the rest
  3. the item is dated 1950 or later                   -- spares Humboldt's own 1838 "Ueber den Manati des
                                                          Orinoko" and Babbage's 1855 Society of Arts journal,
                                                          which clauses 1 and 2 alone condemned
  4. NOT ONE of the subject's paper-collection items   -- spares Euler, 24 of whose arXiv translations match
     matched a work in their researched bibliography      his works list, so his set is not unambiguous

Nothing is deleted. Files move to ~/corpus/misattributed/<slug>/ and the availability verdict is rewritten so
a later fetch does not restore them, both reversible, because Anthony's standing instruction is that removing
a thing from the atlas means archiving it.

    python3 atlas_tools/corpus_demote_papers.py --dry-run
    python3 atlas_tools/corpus_demote_papers.py
"""
import json
import os
import shutil
import sys
from pathlib import Path

CORPUS = Path(os.path.expanduser("~/corpus"))
AVAIL = CORPUS / "availability"
BIB = CORPUS / "bib"
FILES = CORPUS / "files"
QUARANTINE = CORPUS / "misattributed"

PAPERS = {"arxiv", "pubmed", "biorxiv", "medrxiv", "journals", "journals_contributions", "biostor",
          "chemrxiv", "psyarxiv", "socarxiv", "theses-and-dissertations"}
PRE_MODERN_DEATH = 1900
MODERN_IMPRINT = 1950

REASON = ("a research paper published {year}, in a modern paper collection, under a subject who died "
          "{death}: the Archive's creator search matched the NAME, not the person. Moved to "
          "corpus/misattributed/ 2026-10-25, not deleted.")


def main():
    dry = "--dry-run" in sys.argv
    moved = subjects = 0
    missing = 0
    report = []

    for p in sorted(AVAIL.glob("*.json")):
        slug = p.stem
        rec = json.loads(p.read_text(encoding="utf-8"))
        dy = rec.get("death_year")
        if not dy or int(dy) >= PRE_MODERN_DEATH:
            continue
        mp = FILES / slug / "manifest.json"
        bp = BIB / f"{slug}.json"
        if not mp.exists() or not bp.exists():
            continue

        man = json.loads(mp.read_text(encoding="utf-8"))
        on_disk = {k.split(":")[0] for k, v in man.items() if v.get("bytes")}
        bib = json.loads(bp.read_text(encoding="utf-8"))
        matched = {str(e["id"]) for w in (bib.get("works") or []) for e in (w.get("editions") or [])
                   if e.get("id") is not None}

        # Clause 4 is judged over EVERY paper-collection item of this subject, not only the modern ones. Asking
        # it of the modern subset would let a subject through whose older papers matched, which is evidence
        # about the subject and must count.
        all_paper_ids = {str(it.get("id")) for it in rec.get("items", [])
                         if it.get("verdict") == "download" and set(it.get("collection") or []) & PAPERS}
        if all_paper_ids & matched:
            continue

        hits = []
        for it in rec.get("items", []):
            y = it.get("year")
            if (it.get("verdict") == "download"
                    and set(it.get("collection") or []) & PAPERS
                    and y and int(y) >= MODERN_IMPRINT
                    and str(it.get("id")) in on_disk):
                hits.append(it)
        if not hits:
            continue

        subjects += 1
        dest = QUARANTINE / slug
        for it in hits:
            ident = str(it.get("id"))
            key = f"{ident}:text"
            entry = man.get(key) or {}
            rel = entry.get("file")
            src = CORPUS / rel if rel else None
            if src and src.exists():
                if not dry:
                    dest.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest / src.name))
                moved += 1
            else:
                missing += 1
            if not dry:
                man.pop(key, None)
                it["verdict"] = "catalogue"
                it["reason"] = REASON.format(year=it.get("year"), death=dy)
        report.append((len(hits), slug, bib.get("traveler") or slug, int(dy)))

        if not dry:
            mp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
            rec["n_download"] = sum(1 for i in rec["items"] if i.get("verdict") == "download")
            rec["n_catalogue"] = sum(1 for i in rec["items"] if i.get("verdict") == "catalogue")
            p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(("DRY RUN: " if dry else "") +
          f"{moved} files from {subjects} subjects moved to {QUARANTINE}"
          + (f"; {missing} already absent from disk" if missing else ""))
    for n, slug, name, dy in sorted(report, reverse=True)[:25]:
        print(f"  {n:>4}  {slug:<28} {name[:34]:<34} d.{dy}")
    if len(report) > 25:
        print(f"  ... and {len(report)-25} more subjects")


if __name__ == "__main__":
    main()
