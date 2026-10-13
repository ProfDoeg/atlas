#!/usr/bin/env python3
"""Step two of the corpus project: for each long-dead atlas subject, what of theirs is actually free to take?

corpus_inventory.py said WHAT the atlas wrote, offline, out of the dossiers. This asks the open libraries what
exists and, crucially, WHICH EDITIONS may be downloaded.

nodus3's catch, 2026-10-13, and the whole reason this tool is not a one-liner: an author being out of copyright
does not make a file out of copyright. Ficino died in 1499, but the Internet Archive's holdings under his name
include a 1991 Spanish translation and a 2012 critical edition, both of which carry new copyrightable work by
living translators and editors. So the gate is on the EDITION, never on the author.

The gate, deliberately conservative, erring toward cataloguing rather than taking:

  DOWNLOAD only when all of:
    * the author died before 1900 (the inventory's triage; life+70 clears 1956, so this has no argument in it),
    * the item carries an imprint YEAR and that year is before 1930,
    * the item is in none of the Archive's lending collections -- inlibrary, printdisabled, lendinglibrary,
      books-by-lending and the like are controlled digital lending, where the scan is borrowed, not given,
    * the item's possible-copyright-status, where the Archive states one at all, is not "In Copyright".
  CATALOGUE, meaning record where it is and fetch nothing, in every other case, including the large middle
  where the Archive simply gives no year. Of 58 Ficino items, 49 carry no copyright status and several no year;
  silence is not permission.

Project Gutenberg is queried through the gutendex catalog API, never by crawling gutenberg.org, which its terms
forbid. Everything Gutenberg lists is free by construction, so its hits need no gate.

Rate: one request per second per host, with retry and backoff. 199 subjects is about seven minutes, not a crawl.
Resumable: a subject whose file already exists is skipped, so an interrupted run costs nothing.

    python3 atlas_tools/corpus_availability.py --slug marsilio_ficino   # one subject, to the screen
    python3 atlas_tools/corpus_availability.py --limit 20               # the pilot
    python3 atlas_tools/corpus_availability.py                          # all pre-1900 subjects
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CORPUS = Path(os.path.expanduser("~/corpus"))
INVENTORY = CORPUS / "inventory.jsonl"
AVAIL = CORPUS / "availability"
UA = "atlas-corpus/0.1 (private research corpus for the Atlas of Journeys; run from nodus)"

DEATH_CUTOFF = 1900         # author must have died before this to be eligible at all
IMPRINT_CUTOFF = 1930       # and the edition itself must be older than this to be taken
PAUSE = 1.0                 # seconds between requests to one host

# Archive collections that mean "borrowable", not "free". An item in any of these is catalogued, never fetched.
LENDING = {"inlibrary", "printdisabled", "lendinglibrary", "books-by-lending", "bookreader-lending",
           "internetarchivebooks", "daisy", "protected-daisy"}

# Collections fed by scanning institutions. Their imprint metadata comes from a library catalogue and can be
# trusted to describe the physical book that was scanned.
LIBRARY = {"americana", "europeanlibraries", "toronto", "cdl", "library_of_congress", "jcbl", "bostonpubliclibrary",
           "wellcomelibrary", "medicalheritagelibrary", "biodiversity", "universityoffloridaduplicates",
           "universallibrary", "openlibrary", "getty", "smithsonian", "nationallibraryofscotland",
           "JaiGyan", "digitallibraryindia", "cnrs", "bibliothequenationaledefrance"}

# Anyone may upload to opensource/community, and the Archive does not check the metadata. The year field on such
# an item is routinely the AUTHOR'S birth or floruit rather than the edition's imprint: this run found a modern
# English translation of Ficino's Philebus commentary stamped 1433, his birth year, and a commentary stamped 1480.
# Taking those as pre-1930 imprints would download living translators' work. So a user upload is catalogued
# whatever its year claims, unless a scanning institution also holds it.
USER_UPLOAD = {"opensource", "community", "opensource_media", "folksoundomy", "additional_collections"}

IA_FIELDS = ["identifier", "title", "year", "date", "creator", "language", "mediatype",
             "collection", "licenseurl", "rights", "possible-copyright-status", "downloads"]


def fetch(url, tries=4, timeout=40):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"{url} failed after {tries}: {last!r}")


def year_of(doc):
    """An imprint year from `year` or the first 3-4 digit run of `date`, else None. Never guessed."""
    y = doc.get("year")
    if isinstance(y, str) and y.isdigit():
        y = int(y)
    if isinstance(y, int) and 100 <= y <= 2100:
        return y
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(doc.get("date") or ""))
    return int(m.group(1)) if m else None


def verdict(doc, death_year):
    """('download'|'catalogue', reason). The reason is kept so a human can audit any single decision."""
    if death_year is None or death_year >= DEATH_CUTOFF:
        return "catalogue", f"author death {death_year} not before {DEATH_CUTOFF}"
    colls = set(doc.get("collection") or [])
    bad = colls & LENDING
    if bad:
        return "catalogue", "lending collection: " + ", ".join(sorted(bad))
    status = str(doc.get("possible-copyright-status") or "").strip()
    if status and status.upper().replace(" ", "_") not in ("NOT_IN_COPYRIGHT", "PUBLIC_DOMAIN"):
        return "catalogue", f"archive says copyright status {status}"
    if (colls & USER_UPLOAD) and not (colls & LIBRARY):
        return "catalogue", "user upload, imprint metadata unverified"
    y = year_of(doc)
    if y is None:
        return "catalogue", "no imprint year stated"
    if y >= IMPRINT_CUTOFF:
        return "catalogue", f"edition of {y}, not before {IMPRINT_CUTOFF} (modern translation or edition)"
    if y < death_year:
        # An imprint cannot predate its author's death by much; when it does, the field is the author's dates,
        # not the book's. Ficino, died 1499, had items stamped 1433 and 1480.
        return "catalogue", f"stated year {y} precedes the author's death {death_year}: metadata is the author, not the edition"
    return "download", f"edition of {y}, author died {death_year}"


def ia_items(name):
    q = f'creator:("{name}") AND mediatype:texts'
    url = ("https://archive.org/advancedsearch.php?q=" + urllib.parse.quote(q)
           + "".join("&fl%5B%5D=" + f for f in IA_FIELDS)
           + "&rows=200&page=1&output=json")
    d = json.loads(fetch(url))
    return d.get("response", {}).get("docs", []), d.get("response", {}).get("numFound", 0)


def gutenberg_items(name):
    url = "https://gutendex.com/books?search=" + urllib.parse.quote(name)
    d = json.loads(fetch(url))
    out = []
    for b in d.get("results", []):
        authors = "; ".join(a.get("name", "") for a in b.get("authors", []))
        out.append({"source": "gutenberg", "id": b.get("id"), "title": b.get("title"),
                    "creator": authors, "languages": b.get("languages"),
                    "formats": {k: v for k, v in (b.get("formats") or {}).items()
                                if k.startswith(("text/plain", "application/epub", "application/pdf"))},
                    "verdict": "download", "reason": "Project Gutenberg: free by construction"})
    return out


def subjects():
    """slug -> (traveler, death_year) for everyone the inventory found works for."""
    out = {}
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("title"):
                out.setdefault(r["slug"], (r.get("traveler", ""), r.get("death_year")))
    return out


def name_variants(slug, traveler):
    """The names a library might catalogue this person under, most formal first.

    The catalog's traveler string is the atlas's own formal form and is often NOT what a library uses:
    ada_lovelace is "Augusta Ada King, Countess of Lovelace (Ada Byron)", and a creator search on
    "Augusta Ada King" returns nothing at all while "Ada Lovelace" returns shelves. So every query goes out under
    the formal name, any parenthetical alias, and the slug read back as words, and the results are unioned on
    identifier. Querying three ways costs three seconds a subject and is the difference between finding a
    corpus and finding zero.
    """
    out = []
    base = re.sub(r"\s*\(.*?\)\s*", " ", traveler)
    out.append(base.split(",")[0].strip())
    for alias in re.findall(r"\((.*?)\)", traveler):
        for part in alias.split("/"):
            part = part.split(",")[0].strip()
            if len(part.split()) >= 2:
                out.append(part)
    out.append(" ".join(w.capitalize() for w in slug.split("_")))
    seen, uniq = set(), []
    for n in out:
        n = re.sub(r"\s+", " ", n).strip()
        k = n.lower()
        if n and len(n) > 3 and k not in seen:
            seen.add(k)
            uniq.append(n)
    return uniq[:3]


def run_one(slug, traveler, death_year, to_screen=False):
    names = name_variants(slug, traveler)
    name = names[0]
    docs, found, by_id = [], 0, {}
    for nm in names:
        try:
            ds, f = ia_items(nm)
        except Exception:
            ds, f = [], 0
        found = max(found, f)
        for d in ds:
            by_id.setdefault(d.get("identifier"), d)
        time.sleep(PAUSE)
    docs = list(by_id.values())
    items = []
    for d in docs:
        v, why = verdict(d, death_year)
        items.append({"source": "archive.org", "id": d.get("identifier"), "title": d.get("title"),
                      "creator": d.get("creator"), "year": year_of(d), "language": d.get("language"),
                      "collection": d.get("collection"), "status": d.get("possible-copyright-status"),
                      "verdict": v, "reason": why})
    g_seen = set()
    for nm in names:
        try:
            for g in gutenberg_items(nm):
                if g.get("id") not in g_seen:
                    g_seen.add(g.get("id"))
                    items.append(g)
        except Exception as e:                   # gutendex is a courtesy mirror; never let it kill a run
            items.append({"source": "gutenberg", "error": repr(e), "verdict": "catalogue",
                          "reason": "gutendex unreachable"})
        time.sleep(PAUSE)
    rec = {"slug": slug, "traveler": traveler, "queried_as": names, "death_year": death_year,
           "ia_num_found": found, "items": items,
           "n_download": sum(1 for i in items if i.get("verdict") == "download"),
           "n_catalogue": sum(1 for i in items if i.get("verdict") == "catalogue")}
    AVAIL.mkdir(parents=True, exist_ok=True)
    (AVAIL / f"{slug}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    if to_screen:
        from collections import Counter
        print(f"{traveler}\n  queried as {names}, died {death_year}; the Archive holds {found}")
        print(f"  clear to download {rec['n_download']}, catalogue only {rec['n_catalogue']}\n")
        for i in items:
            if i.get("verdict") == "download":
                print("  TAKE  %-38s %-6s %s" % (str(i.get("id"))[:38], i.get("year"), str(i.get("title"))[:44]))
        print("\n  why the rest were left:")
        for why, n in Counter(i.get("reason", "") for i in items if i.get("verdict") == "catalogue").most_common(8):
            print("   %4d  %s" % (n, why))
        print(f"\n  wrote {AVAIL / (slug + '.json')}")
    return rec


def main():
    subs = subjects()
    if "--slug" in sys.argv:
        s = sys.argv[sys.argv.index("--slug") + 1]
        tr, dy = subs.get(s, ("", None))
        run_one(s, tr, dy, to_screen=True)
        return
    # Every subject, not only the long-dead. Anthony, 2026-10-13: "Compile a full bibliography for each person
    # of books they have written. Download when possible." The catalogue is wanted for everyone; the gate above
    # already refuses to fetch anything by an author who died after 1900, so running the query wide is safe and
    # is what turns this from a download list into a bibliography.
    todo = sorted((s, t, d) for s, (t, d) in subs.items())
    if "--free-only" in sys.argv:
        todo = [r for r in todo if r[2] and r[2] < DEATH_CUTOFF]
    if "--limit" in sys.argv:
        todo = todo[: int(sys.argv[sys.argv.index("--limit") + 1])]
    AVAIL.mkdir(parents=True, exist_ok=True)
    done = tot_d = tot_c = 0
    for slug, tr, dy in todo:
        if (AVAIL / f"{slug}.json").exists():
            continue
        try:
            rec = run_one(slug, tr, dy)
        except Exception as e:
            print(f"  {slug}: FAILED {e!r}", flush=True)
            continue
        done += 1
        tot_d += rec["n_download"]
        tot_c += rec["n_catalogue"]
        print(f"  {slug:<34} found {rec['ia_num_found']:>5}  download {rec['n_download']:>4}  "
              f"catalogue {rec['n_catalogue']:>4}", flush=True)
    print(f"\n{done} subjects queried; {tot_d} items clear to download, {tot_c} catalogue-only")
    print(f"per-subject records in {AVAIL}")


if __name__ == "__main__":
    main()
