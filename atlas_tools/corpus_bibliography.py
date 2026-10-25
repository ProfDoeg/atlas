#!/usr/bin/env python3
"""A BibTeX bibliography per atlas subject: one entry per WORK, with its editions attached underneath.

Anthony, 2026-10-13: "Compile a full bibliography for each person of books they have written" -- then "Bibtex" --
then, seeing the first cut, "I think we need to consult scholarship to determine the books someone has written.
There will be many duplicates if you just websearch or library search."

He was right, and the first cut proved it. Generated from Open Library, Giordano Bruno came out with 212
"works", of which 190 rested on nothing but a catalogue row and only 6 had any scholarly backing. The list held
"La cena de las cenizas" and "LA CENA DE LE CENERI" as two separate works; they are one dialogue in two
languages. "De la Causa, Principio et Uno" appeared three times. A library catalogue is a list of EDITIONS --
printings, translations, anthologies, and a good deal of writing ABOUT the author rather than by them -- and
counting its rows is not a bibliography.

So the hierarchy is inverted from the first version, and the inversion is the whole point of this file:

  A WORK may only be created by scholarship. In practice that is the dossier's researched "Works by" section,
  which was built against cited sources. Nothing else can mint a work.

  AN EDITION is what a library holds. Open Library works, Internet Archive items and Gutenberg books are matched
  against the known works and attached underneath as editions, carrying the download status and URL. They can
  never create a new entry.

  THE UNMATCHED are library holdings that fit no known work. They are not discarded and not promoted: they go to
  ~/corpus/unmatched/<slug>.json for a human to look at. That file is where a genuinely missing work will show
  up, and where the books-about-him noise collects.

Matching is by folded title, either containment or a token overlap above MATCH_RATIO. It will NOT match across
languages -- "cena de le ceneri" and "cena de las cenizas" share almost no tokens -- and that is left as it is
rather than papered over with a translation table that would guess. Such editions land in the unmatched file,
which is the honest place for them.

Where a subject has NO dossier works section, this produces an empty bibliography and says so, loudly, in the
run summary. That is a research gap to be filled by researching the person's bibliography properly -- it is not
an invitation to fall back on catalogue rows. Michelangelo and Francis Bacon are both in that state.

    python3 atlas_tools/corpus_bibliography.py --slug giordano_bruno
    python3 atlas_tools/corpus_bibliography.py --limit 20
    python3 atlas_tools/corpus_bibliography.py              # resumes: skips subjects already written
    python3 atlas_tools/corpus_bibliography.py --rebuild    # rewrites all, after the inventory changes
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
UNMATCHED = CORPUS / "unmatched"
FILES = CORPUS / "files"
OL_WORK_CAP = 600
DEATH_TOLERANCE = 2
MATCH_RATIO = 0.6          # token overlap, relative to the shorter title, to call two titles the same work

STOPWORDS = {"the", "a", "an", "of", "on", "in", "to", "and", "le", "la", "el", "il", "de", "del", "di",
             "der", "das", "die", "des", "een", "un", "una", "y", "et", "ou", "or", "con", "da", "du",
             "liber", "libri", "opera", "works", "book", "books"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|a|an|le|la|el|il|de|der|das|die) ", "", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s):
    return {w for w in norm(s).split() if w not in STOPWORDS and len(w) > 2}


def same_work(a, b, author_tokens=frozenset()):
    """Is this library title an edition of this known work?

    The author's own name tokens are removed from both titles first. Without that, "Opere di Giordano Bruno
    Nolano" and the biography "Giordano-Bruno-Buch" share two of three tokens and the biography is filed as an
    edition of the collected works. The author's name in a title carries no information about WHICH work it is,
    on either side, and books about a person are precisely what a creator search drags in.
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a) - author_tokens, tokens(b) - author_tokens
    if not ta or not tb:
        return False
    # Containment, but only once the name is gone, so "Candelaio" still matches "Il candelaio commedia".
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / min(len(ta), len(tb)) >= MATCH_RATIO


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


def ol_author(names, death_year):
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
                        "year": first_year(e.get("first_publish_date")), "source": "openlibrary"})
        if len(entries) < 200:
            break
        offset += 200
    return out[:OL_WORK_CAP]


def esc(s):
    s = str(s or "").replace("\\", "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", s).strip()


def bib_author(slug, traveler):
    """'Bruno, Giordano' from 'Giordano Bruno (Filippo Bruno, il Nolano)'. The surname is located by the slug's
    last token, because the atlas's display names bury it: ada_lovelace is 'Augusta Ada King, Countess of
    Lovelace (Ada Byron)'."""
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
    surname, given = " ".join(words[idx:]), " ".join(words[:idx])
    return esc(f"{surname}, {given}" if given else surname)


def bibkey(slug, work, used):
    surname = re.sub(r"[^a-z0-9]", "", slug.split("_")[-1]) or "anon"
    year = str(work.get("year") or "nd")
    words = [w for w in norm(work["title"]).split() if w not in STOPWORDS]
    short = (words[0] if words else "untitled")[:14]
    base, key, n = f"{surname}{year}{short}", f"{surname}{year}{short}", 1
    while key in used:
        n += 1
        key = f"{base}{chr(ord('a') + n - 2)}"
    used.add(key)
    return key


def local_files(slug):
    """edition id -> relative path, from whatever corpus_fetch has already pulled down."""
    mp = FILES / slug / "manifest.json"
    if not mp.exists():
        return {}
    out = {}
    for k, v in json.loads(mp.read_text(encoding="utf-8")).items():
        if isinstance(v, dict) and v.get("file"):
            out[k.split(":")[0]] = v["file"]
    return out


def build(slug, traveler, death_year, avail):
    names = AV.name_variants(slug, traveler)
    author, verified = ol_author(names, death_year)

    works = []
    for r in dossier_works(slug):
        works.append({"title": r["title"], "year": r.get("year"), "kind": r.get("kind"),
                      "date_text": r.get("date_text"), "alt_titles": r.get("alt_titles") or [],
                      "authority": "atlas dossier", "editions": []})

    have = local_files(slug)
    pool = []
    if author and author.get("key"):
        pool += ol_works(author["key"])
    for it in (avail or {}).get("items", []):
        if it.get("source") == "archive.org":
            pool.append({"title": it.get("title"), "year": it.get("year"), "source": "archive.org",
                         "id": it.get("id"), "verdict": it.get("verdict"), "reason": it.get("reason"),
                         "url": f"https://archive.org/details/{it.get('id')}"})
        elif it.get("source") == "gutenberg" and it.get("id"):
            pool.append({"title": it.get("title"), "year": it.get("year"), "source": "gutenberg",
                         "id": it.get("id"), "verdict": it.get("verdict"), "reason": it.get("reason"),
                         "url": f"https://www.gutenberg.org/ebooks/{it.get('id')}"})

    # Every form of the person's own name, so it cannot be mistaken for title evidence on either side.
    atok = set()
    for nm in names + [traveler]:
        atok |= {w for w in norm(nm).split() if len(w) > 2}

    unmatched = []
    for cand in pool:
        hit = None
        for w in works:
            if (same_work(cand["title"], w["title"], atok)
                    or any(same_work(cand["title"], a, atok) for a in w["alt_titles"])):
                hit = w
                break
        if hit is None:
            unmatched.append(cand)
            continue
        ed = dict(cand)
        if cand.get("id") and cand["id"] in have:
            ed["file"] = have[cand["id"]]
        hit["editions"].append(ed)

    return {"slug": slug, "traveler": traveler, "death_year": death_year,
            "openlibrary_author": (author or {}).get("key"),
            "author_verified_by_death_year": verified, "queried_as": names,
            "n_works": len(works), "n_editions": sum(len(w["editions"]) for w in works),
            "n_unmatched": len(unmatched), "works": works}, unmatched


def status_of(work):
    eds = work["editions"]
    if any(e.get("file") for e in eds):
        return "downloaded"
    if any(e.get("verdict") == "download" for e in eds):
        return "free edition located, not yet fetched"
    if eds:
        return "editions located but none free: in copyright, lending-only, or undated"
    return "no edition located in the open libraries"


def to_bibtex(rec):
    """biblioteca's house format: UTF-8 for biblatex + biber, aligned fields, double-braced titles, annote
    carrying the annotation. One entry per WORK; its editions live in annote and url."""
    head = [f"% {rec['traveler']} -- {rec['n_works']} works, {rec['n_editions']} editions attached",
            "% generated by atlas_tools/corpus_bibliography.py. UTF-8: compile with biblatex + biber.",
            "% WORKS come from the atlas dossier's researched bibliography and from nowhere else.",
            "% Library holdings (Open Library, Internet Archive, Gutenberg) are attached as EDITIONS only;",
            f"% {rec['n_unmatched']} holdings matched no known work and are in ~/corpus/unmatched/{rec['slug']}.json"]
    if not rec["n_works"]:
        head.append("% NO WORKS: this subject's dossier has no researched works section. That is a gap to be")
        head.append("% filled by scholarship, not by catalogue rows, so this file is deliberately empty.")
    used, out = set(), []
    for w in rec["works"]:
        f = [f"  author     = {{{bib_author(rec['slug'], rec['traveler'])}}}",
             f"  title      = {{{{{esc(w['title'])}}}}}"]
        if w.get("year"):
            f.append(f"  year       = {{{w['year']}}}")
        if w.get("kind"):
            f.append(f"  type       = {{{esc(w['kind'])}}}")
        free = [e for e in w["editions"] if e.get("verdict") == "download" or e.get("file")]
        if free:
            f.append(f"  url        = {{{free[0].get('url', '')}}}")
        got = [e for e in w["editions"] if e.get("file")]
        if got:
            f.append(f"  file       = {{{got[0]['file']}}}")
        note = []
        if w.get("date_text"):
            note.append(f"dated by the dossier: {esc(w['date_text'])}")
        note.append(status_of(w))
        f.append(f"  note       = {{{'; '.join(note)}}}")
        f.append(f"  keywords   = {{{esc(w['authority'])}}}")
        ann = [f"{esc(rec['traveler'])}. Established by the {esc(w['authority'])}."]
        if w["editions"]:
            ann.append(f"{len(w['editions'])} edition(s) located: "
                       + "; ".join(f"{esc(e['title'])[:60]} ({e.get('year') or 'n.d.'}, {e['source']})"
                                   for e in w["editions"][:6])
                       + (" ..." if len(w["editions"]) > 6 else ""))
        else:
            ann.append("No edition located in the open libraries.")
        f.append(f"  annote     = {{{' '.join(ann)}}}")
        out.append("@book{" + bibkey(rec["slug"], w, used) + ",\n" + ",\n".join(f) + "\n}")
    return "\n".join(head + out) + "\n"


def main():
    subs = {}
    with open(INVENTORY, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            subs.setdefault(r["slug"], (r.get("traveler", ""), r.get("death_year")))
    todo = sorted(subs.items())
    if "--slug" in sys.argv:
        s = sys.argv[sys.argv.index("--slug") + 1]
        todo = [(s, subs.get(s, ("", None)))]
    elif "--limit" in sys.argv:
        todo = todo[: int(sys.argv[sys.argv.index("--limit") + 1])]

    BIB.mkdir(parents=True, exist_ok=True)
    UNMATCHED.mkdir(parents=True, exist_ok=True)
    tot_w = tot_e = tot_u = 0
    gaps = []
    for slug, (tr, dy) in todo:
        # An existing .bib is normally taken as done, which is what makes a long run resumable. But the works
        # come from the inventory, and when the inventory changes every stored bibliography is stale -- the
        # prose-extraction pass added 6,244 works and not one of them would have reached a .bib file. Same
        # shape as a verdict left behind after its gate moved, so it gets the same answer: an explicit flag
        # that rebuilds from the current inventory rather than a number nobody notices is out of date.
        if (BIB / f"{slug}.bib").exists() and "--slug" not in sys.argv and "--rebuild" not in sys.argv:
            continue
        ap = AV.AVAIL / f"{slug}.json"
        avail = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else None
        try:
            rec, unmatched = build(slug, tr, dy, avail)
        except Exception as e:
            print(f"  {slug}: FAILED {e!r}", flush=True)
            continue
        (BIB / f"{slug}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        (BIB / f"{slug}.bib").write_text(to_bibtex(rec), encoding="utf-8")
        (UNMATCHED / f"{slug}.json").write_text(
            json.dumps({"slug": slug, "traveler": tr, "items": unmatched}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        tot_w += rec["n_works"]
        tot_e += rec["n_editions"]
        tot_u += rec["n_unmatched"]
        if not rec["n_works"]:
            gaps.append(slug)
        print(f"  {slug:<34} works {rec['n_works']:>4}  editions {rec['n_editions']:>4}  "
              f"unmatched {rec['n_unmatched']:>4}", flush=True)
    print(f"\n{tot_w} works, {tot_e} editions attached, {tot_u} library holdings unmatched")
    print(f"bibliographies in {BIB}; unmatched holdings in {UNMATCHED}")
    if gaps:
        print(f"\n{len(gaps)} subjects have NO researched works section and so an empty bibliography.")
        print("These need their bibliography researched, not guessed from catalogues:")
        print("  " + ", ".join(gaps[:30]) + (" ..." if len(gaps) > 30 else ""))


if __name__ == "__main__":
    main()
