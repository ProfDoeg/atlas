#!/usr/bin/env python3
"""Re-judge every stored edition under the private-study policy, without re-querying anything.

Anthony, 2026-10-24: "It's for private study, fair use, non-commercial purposes." That settles the question the
death-year gate was standing in for. The gate was mine, not the Archive's: I set it at "author died before
1900" because it is unarguable under any regime, and it refused 24,797 editions that are in fact downloadable.
Refusing them was a policy choice, and the policy is his to set.

WHAT CHANGES. The two COPYRIGHT gates come off: the author's death year and the edition's imprint year. Those
were proxies for "is this safe to publish", and nothing here is published -- the corpus lives in ~/corpus,
outside every repository, and only the bibliography is in git.

WHAT DOES NOT CHANGE, and why each one stays:

  lending collections     Not a policy at all. Controlled digital lending serves a borrower one page at a time
                          and never hands over a file. These cannot be downloaded by anyone at any setting, so
                          relaxing our rules does not move them.
  about, not by           A correctness rule, not a copyright one. Anthony: "If we allow every book ABOUT a
                          person it wil blow up the project. Works BY the person." A biography of Columbus
                          filed under Columbus is wrong whatever the licence.
  explicit In Copyright   Where the Archive itself states the status, we take its word rather than overriding
                          a statement from the holder of the file.
  error placeholders      Not an edition at all. When gutendex is unreachable corpus_availability records a
                          stub -- {"source": "gutenberg", "error": ..., "verdict": "catalogue"} -- so the run
                          is not killed by a courtesy mirror. That stub has no id and no formats, so there is
                          nothing to fetch, and an earlier version of this tool promoted 45 of them to
                          "download" because they carried no lending collection and no copyright status. They
                          were unfetchable, so no file was missed; what was damaged was the COUNT, which
                          claimed 642 subjects had free editions when 597 did. A second pass below demotes any
                          already-promoted stub, so re-running this tool repairs old records as well.

The verdict reason is rewritten in every case so the record says WHY an item is now takeable, and the catalogue
keeps telling the truth about what each thing is. Nothing is re-fetched here; this only re-labels. Run
corpus_fetch.py afterwards to collect what has newly opened.

    python3 atlas_tools/corpus_reverdict.py --dry-run
    python3 atlas_tools/corpus_reverdict.py
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

AVAIL = Path(os.path.expanduser("~/corpus/availability"))
LENDING = {"inlibrary", "printdisabled", "lendinglibrary", "books-by-lending", "bookreader-lending",
           "internetarchivebooks", "daisy", "protected-daisy"}


def unfetchable(it):
    """True when there is no file to ask for, whatever the copyright position.

    An item is a pointer to bytes somewhere. Without an id there is no URL to build, and a Gutenberg hit
    without formats names no file. Both shapes come from the error stub corpus_availability writes when
    gutendex is unreachable; neither is an edition, so neither belongs in a download count.
    """
    if it.get("error"):
        return True
    if it.get("id") in (None, "", "None"):
        return True
    return it.get("source") == "gutenberg" and not (it.get("formats") or {})


def main():
    dry = "--dry-run" in sys.argv
    opened = kept = demoted = 0
    why_kept = Counter()

    for p in sorted(AVAIL.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        changed = False
        for it in rec.get("items", []):
            # Repair first: an earlier run of this tool promoted error stubs. Demote them wherever they sit,
            # so the count stops over-reporting without anyone having to re-query the catalogues.
            if it.get("verdict") == "download" and unfetchable(it):
                it["verdict"] = "catalogue"
                it["reason"] = ("not an edition: catalogue lookup failed, so this record names no file to "
                                "fetch; demoted from download 2026-10-25")
                demoted += 1
                changed = True
                continue
            if it.get("verdict") != "catalogue":
                continue
            if unfetchable(it):
                why_kept["no file to fetch: catalogue lookup failed"] += 1
                kept += 1
                continue
            reason = str(it.get("reason", ""))
            colls = set(it.get("collection") or [])

            if colls & LENDING:
                why_kept["lending: no file is served to anyone"] += 1
                kept += 1
                continue
            if "ABOUT the subject" in reason or "another person of the same name" in reason:
                why_kept["about the subject, not by them"] += 1
                kept += 1
                continue
            # The Archive's status field is prose as often as a code, and some of that prose is PERMISSIVE:
            # "The Library of Congress is unaware of any copyright restrictions for this item" and "Public
            # domain. The BHL considers that this work is no longer under copyright protection" were both
            # being withheld by an exact match against two code strings. Read the sense, not the token.
            status = str(it.get("status") or "").strip()
            permissive = any(s in status.lower() for s in
                             ("not_in_copyright", "public domain", "no copyright restriction",
                              "unaware of any copyright", "no known copyright"))
            if status and not permissive:
                why_kept[f"archive states: {status}"] += 1
                kept += 1
                continue
            if it.get("source") == "gutenberg" and "author is" in reason:
                why_kept["about the subject, not by them"] += 1
                kept += 1
                continue

            it["verdict"] = "download"
            it["reason"] = ("private study, non-commercial: copyright gates lifted on Anthony's instruction "
                            "2026-10-24; the file is served and is the subject's own work")
            opened += 1
            changed = True

        if changed and not dry:
            rec["n_download"] = sum(1 for i in rec["items"] if i.get("verdict") == "download")
            rec["n_catalogue"] = sum(1 for i in rec["items"] if i.get("verdict") == "catalogue")
            p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(("DRY RUN: " if dry else "")
          + f"{opened} editions opened for download; {kept} still withheld; "
            f"{demoted} unfetchable stubs demoted")
    for k, v in why_kept.most_common(7):
        print(f"  {v:6d}  {k}")
    if not dry:
        print("\nrun corpus_fetch.py to collect them")


if __name__ == "__main__":
    main()
