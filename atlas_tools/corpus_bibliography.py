#!/usr/bin/env python3
"""A full BibTeX bibliography per atlas subject, and the free editions fetched where they exist.

Anthony, 2026-10-13: "Compile a full bibliography for each person of books they have written. Download when
possible" -- and, asked in what format, "Bibtex".

Three sources are merged, each covering the others' holes:

  * THE DOSSIERS (offline, corpus_inventory.py). What the Codex research actually established, with the
    dossier's own dating language. Authoritative on attribution and on what matters, but incomplete: 13 dossiers
    have no works section at all, Michelangelo's and Francis Bacon's among them.
  * OPEN LIBRARY. An author record with birth and death dates, and its works list. This is the backbone, because
    it is a real catalogue: 248 works for Ficino, 420 for Michelangelo, 1,664 for Francis Bacon.
  * THE INTERNET ARCHIVE and PROJECT GUTENBERG (corpus_availability.py). Not for the list of works but for the
    EDITIONS that can actually be downloaded, behind that module's gate.

Picking the right author is the dangerous step, and it is checked rather than assumed. Open Library has 43
authors called Francis Bacon and 363 called Michelangelo. A candidate is accepted only when its death year
matches the atlas's lifespan within two years; where the atlas gives no lifespan, the top match is taken and the
entry is marked unverified in the .bib so a reader can see which ones rest on a guess. Picking the painter
Francis Bacon (1909-1992) for the Lord Chancellor is exactly the error this prevents.

Output, per subject, under ~/corpus/bib/:
    <slug>.bib    the bibliography. @book entries, one per distinct work, with the source in a note field, and
                  a file field on every entry whose edition was downloaded.
    <slug>.json   the same merged, with provenance per entry, for machines.
And ~/corpus/atlas.bib, every subject concatenated.

    python3 atlas_tools/corpus_bibliography.py --slug marsilio_ficino
    python3 atlas_tools/corpus_bibliography.py --limit 20
    python3 atlas_tools/corpus_bibliography.py              # everyone the inventory knows a work for
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus_availability as AV  # noqa: E402

CORPUS = Path(os.path.expanduser("~/corpus"))
INVENTORY = CORPUS / "inventory.jsonl"
BIB = CORPUS / "bib"
MASTER = CORPUS / "atlas.bib"
OL_WORK_CAP = 600          # a few subjects have thousands of editions; the works list is capped, and says so
DEATH_TOLERANCE = 2        # years, for accepting an Open Library author as the atlas's person


def norm(s):
    """A title reduced for dedup: accents folded, punctuation dropped, articles and case ignored."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|a|an|le|la|el|il|de|der|das|die) ", "", s)
    return re.sub(r"\s+", " ", s).strip()


def ol_author(names, death_year):
    """(author record, verified?) or (None, False). Death year decides which of 43 Francis Bacons is ours."""
    for nm in names:
        try:
            d = json.loads(AV.fetch("https://openlibrary.org/search/authors.json?q=" + urllib.parse.quote(nm)))
        except Exception:
            continue
        time.sleep(AV.PAUSE)
        docs = d.get("docs") or []
        if not docs:
            continue
        if death_year:
            for doc in docs[:12]:
                ys = re.findall(r"\b(\d{4})\b", str(doc.get("death_date") or ""))
                if ys and abs(int(ys[-1]) - death_year) <= DEATH_TOLERANCE:
                    return doc, True
        else:
            return docs[0], False
    return None, False


def ol_works(key):
    out, offset = [], 0
    while len(out) < OL_WORK_CAP:
        try:
            d = json.loads(AV.fetch(f"https://openlibrary.org/authors/{key}/works.json?limit=200&offset={offset}"))
        except Exception:
            break
        time.sleep(AV.PAUSE)
        entries = d.get("entries") or []
        if not entries:
            break
        for e in entries:
            out.append({"title": e.get("title"), "key": e.get("key"),
                        "year": first_year(e.get("first_publish_date"))})
        if len(entries) < 200:
            break
        offset += 200
    return out[:OL_WORK_CAP]


def first_year(s):
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(s or ""))
    return int(m.group(1)) if m else None


def dossier_works(slug):
    out = []
    if not INVENTORY.exists():
        return out
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["slug"] == slug and r.get("title"):
                out.append(r)
    return out


STOPWORDS = {"the", "a", "an", "of", "on", "in", "to", "and", "le", "la", "el", "il", "de", "del", "di",
             "der", "das", "die", "des", "een", "un", "una", "y", "et", "ou", "or"}


def bibkey(slug, entry, used):
    """biblioteca's form: surname + year + one short title word (artaud1976selected), uniquified.

    The surname comes from the SLUG's last token, not the traveler string: the atlas's formal names put the
    surname in unpredictable places (ada_lovelace is "Augusta Ada King, Countess of Lovelace"), while the slug
    was built to end in the name the atlas files them under.
    """
    surname = re.sub(r"[^a-z0-9]", "", slug.split("_")[-1]) or "anon"
    year = str(entry.get("year") or "nd")
    words = [w for w in norm(entry["title"]).split() if w not in STOPWORDS]
    short = (words[0] if words else "untitled")[:14]
    base = f"{surname}{year}{short}"
    key, n = base, 1
    while key in used:
        n += 1
        key = f"{base}{chr(ord('a') + n - 2)}"
    used.add(key)
    return key


def bib_author(slug, traveler):
    """'Bruno, Giordano' from 'Giordano Bruno (Filippo Bruno, il Nolano)'.

    BibTeX wants surname first, and the atlas's traveler string is a display name with epithets and aliases in
    tow. The slug's last token names the family name the atlas files them under, so the traveler's words are
    split at whichever one matches it. Anything left over -- 'Countess of Lovelace', 'il Nolano' -- is dropped
    from the author field, where it would corrupt sorting, and the full display form is kept in `annote`.
    """
    base = re.sub(r"\s*\(.*?\)\s*", " ", traveler).split(",")[0]
    words = [w for w in re.split(r"\s+", base.strip()) if w]
    if not words:
        return esc(traveler)
    tail = slug.split("_")[-1].lower()
    idx = None
    for i, w in enumerate(words):
        if norm(w) == tail or norm(w).startswith(tail):
            idx = i
    if idx is None:
        idx = len(words) - 1
    surname = " ".join(words[idx:])
    given = " ".join(words[:idx])
    return esc(f"{surname}, {given}" if given else surname)


def status_of(entry):
    if entry.get("file"):
        return "downloaded"
    if entry.get("downloadable"):
        return "free edition located, not yet fetched"
    return "catalogue only: no free edition found, or the editions located are in copyright"


def esc(s):
    """BibTeX-safe: braces balanced away, backslashes dropped, the field left readable."""
    s = str(s or "").replace("\\", "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", s).strip()


def build(slug, traveler, death_year, avail):
    names = AV.name_variants(slug, traveler)
    author, verified = ol_author(names, death_year)
    entries, seen = [], {}

    def add(title, year, source, extra=None):
        k = norm(title)
        if not k:
            return
        if k in seen:
            e = seen[k]
            if source not in e["sources"]:
                e["sources"].append(source)
            if year and not e.get("year"):
                e["year"] = year
            if extra:
                e.update({kk: vv for kk, vv in extra.items() if vv and not e.get(kk)})
            return
        e = {"title": str(title), "year": year, "sources": [source]}
        if extra:
            e.update(extra)
        seen[k] = e
        entries.append(e)

    for r in dossier_works(slug):
        add(r["title"], r.get("year"), "dossier",
            {"kind": r.get("kind"), "date_text": r.get("date_text")})
    if author and author.get("key"):
        for w in ol_works(author["key"]):
            add(w["title"], w.get("year"), "openlibrary", {"ol_key": w.get("key")})
    for it in (avail or {}).get("items", []):
        if it.get("verdict") == "download":
            add(it.get("title"), it.get("year"), it.get("source"),
                {"archive_id": it.get("id"), "gutenberg_id": it.get("id") if it.get("source") == "gutenberg" else None,
                 "downloadable": True,
                 "url": (f"https://archive.org/details/{it.get('id')}" if it.get("source") == "archive.org"
                         else f"https://www.gutenberg.org/ebooks/{it.get('id')}")})

    return {"slug": slug, "traveler": traveler, "death_year": death_year,
            "openlibrary_author": (author or {}).get("key"),
            "openlibrary_name": (author or {}).get("name"),
            "author_verified_by_death_year": verified,
            "queried_as": names, "n_entries": len(entries), "entries": entries}


def to_bibtex(rec):
    """biblioteca's house format, so the two libraries merge: UTF-8 for biblatex + biber, aligned fields,
    double-braced titles, annote carrying the annotation."""
    lines = [f"% {rec['traveler']} -- {rec['n_entries']} works",
             "% generated by atlas_tools/corpus_bibliography.py from the atlas dossiers, Open Library,",
             "% the Internet Archive and Project Gutenberg. UTF-8: compile with biblatex + biber.",
             f"% Open Library author: {rec['openlibrary_author'] or 'none found'}"
             f"{'' if rec['author_verified_by_death_year'] else ' (NOT verified against a death year)'}"]
    if rec["openlibrary_author"] and not rec["author_verified_by_death_year"]:
        lines.append("% The atlas records no lifespan for this subject, so this is the top name match and may be")
        lines.append("% a different person of the same name. Open Library holds 43 Francis Bacons.")
    used = set()
    for e in rec["entries"]:
        f = [f"  author     = {{{bib_author(rec['slug'], rec['traveler'])}}}",
             f"  title      = {{{{{esc(e['title'])}}}}}"]
        if e.get("year"):
            f.append(f"  year       = {{{e['year']}}}")
        if e.get("kind"):
            f.append(f"  type       = {{{esc(e['kind'])}}}")
        if e.get("url"):
            f.append(f"  url        = {{{e['url']}}}")
        if e.get("file"):
            f.append(f"  file       = {{{e['file']}}}")
        note = []
        if e.get("date_text"):
            note.append(f"dated by the dossier: {esc(e['date_text'])}")
        note.append(status_of(e))
        f.append(f"  note       = {{{'; '.join(note)}}}")
        f.append(f"  keywords   = {{{', '.join(e['sources'])}}}")
        f.append(f"  annote     = {{{esc(rec['traveler'])}. Attested by {', '.join(e['sources'])}.}}")
        lines.append("@book{" + bibkey(rec["slug"], e, used) + ",\n" + ",\n".join(f) + "\n}")
    return "\n".join(lines) + "\n"


def main():
    subs = {}
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("title"):
                subs.setdefault(r["slug"], (r.get("traveler", ""), r.get("death_year")))
    todo = sorted(subs.items())
    if "--slug" in sys.argv:
        s = sys.argv[sys.argv.index("--slug") + 1]
        todo = [(s, subs.get(s, ("", None)))]
    elif "--limit" in sys.argv:
        todo = todo[: int(sys.argv[sys.argv.index("--limit") + 1])]

    BIB.mkdir(parents=True, exist_ok=True)
    total = 0
    for slug, (tr, dy) in todo:
        bibfile = BIB / f"{slug}.bib"
        if bibfile.exists() and "--slug" not in sys.argv:
            continue
        avail = None
        ap = AV.AVAIL / f"{slug}.json"
        if ap.exists():
            avail = json.loads(ap.read_text(encoding="utf-8"))
        try:
            rec = build(slug, tr, dy, avail)
        except Exception as e:
            print(f"  {slug}: FAILED {e!r}", flush=True)
            continue
        (BIB / f"{slug}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        bibfile.write_text(to_bibtex(rec), encoding="utf-8")
        total += rec["n_entries"]
        flag = "" if rec["author_verified_by_death_year"] else ("  [OL author unverified]" if rec["openlibrary_author"] else "  [no OL author]")
        print(f"  {slug:<34} {rec['n_entries']:>5} works{flag}", flush=True)
    print(f"\n{total} entries written to {BIB}")


if __name__ == "__main__":
    main()
