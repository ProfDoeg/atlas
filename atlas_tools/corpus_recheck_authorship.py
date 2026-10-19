#!/usr/bin/env python3
"""Re-judge every downloaded Gutenberg item against the author test, and move the ones that fail.

Anthony, 2026-10-19: "If we allow every book ABOUT a person it wil blow up the project. Works BY the person."

gutendex searches titles as well as authors, and corpus_availability was taking every hit as the subject's own
work because everything on Gutenberg is free. Free says nothing about who wrote it. The result: 34 books filed
under Jesus that are about him -- Strauss's "Life of Jesus Critically Examined", the Book of Mormon, a life of
St Teresa OF JESUS who is a different person -- and 2,857 such files across the corpus, better than a quarter of
everything fetched.

The gate is fixed in corpus_availability.py. This repairs what the old gate already let through, WITHOUT
re-querying anything: the stored availability records carry each Gutenberg item's author list, so the new test
can be applied to them offline.

Nothing is deleted. A file that fails moves to ~/corpus/about_not_by/<slug>/, where it stays available as what
it actually is -- a book about the subject, which is worth having and is simply not their work -- and its
manifest entry is rewritten to say so. The Internet Archive path is untouched: it searches creator:(), an
author field, so it never had this failure.

    python3 atlas_tools/corpus_recheck_authorship.py --dry-run
    python3 atlas_tools/corpus_recheck_authorship.py
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

CORPUS = Path(os.path.expanduser("~/corpus"))
AVAIL = CORPUS / "availability"
FILES = CORPUS / "files"
ABOUT = CORPUS / "about_not_by"


def name_parts(s):
    return {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", str(s or ""))}


def main():
    dry = "--dry-run" in sys.argv
    moved = kept = 0
    by_subject = {}

    for ap in sorted(AVAIL.glob("*.json")):
        rec = json.loads(ap.read_text(encoding="utf-8"))
        slug = rec["slug"]
        subject_words = set()
        for n in rec.get("queried_as") or []:
            subject_words |= name_parts(n)
        subject_words |= name_parts(rec.get("traveler"))

        bad_ids, changed = set(), False
        for it in rec.get("items", []):
            if it.get("source") != "gutenberg" or not it.get("id"):
                continue
            by_them = bool(subject_words & name_parts(it.get("creator")))
            if not by_them and it.get("verdict") == "download":
                it["verdict"] = "catalogue"
                it["reason"] = (f"author is {it.get('creator') or 'unstated'}: a book ABOUT the subject, "
                                "or another person of the same name")
                bad_ids.add(str(it["id"]))
                changed = True
        if changed and not dry:
            rec["n_download"] = sum(1 for i in rec["items"] if i.get("verdict") == "download")
            rec["n_catalogue"] = sum(1 for i in rec["items"] if i.get("verdict") == "catalogue")
            ap.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

        mp = FILES / slug / "manifest.json"
        if not bad_ids or not mp.exists():
            continue
        man = json.loads(mp.read_text(encoding="utf-8"))
        hit = 0
        for key, v in list(man.items()):
            if not isinstance(v, dict) or not v.get("file"):
                continue
            if "gutenberg" not in str(v.get("url", "")):
                kept += 1
                continue
            if key.split(":")[0] not in bad_ids:
                kept += 1
                continue
            src = CORPUS / v["file"]
            dst = ABOUT / slug / Path(v["file"]).name
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.move(str(src), str(dst))
                man[key] = {**v, "file": str(dst.relative_to(CORPUS)), "about_not_by": True,
                            "note": "moved: Gutenberg hit on the name, not authored by the subject"}
            moved += 1
            hit += 1
        if hit and not dry:
            mp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
        if hit:
            by_subject[slug] = hit

    print(("DRY RUN: " if dry else "") + f"{moved} files are about the subject rather than by them; "
          f"{kept} stand as authored")
    for slug, n in sorted(by_subject.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {slug:<34} {n}")
    if not dry:
        print(f"\nmoved to {ABOUT}")


if __name__ == "__main__":
    main()
