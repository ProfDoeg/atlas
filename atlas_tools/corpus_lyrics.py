#!/usr/bin/env python3
"""Tango lyrics into the private corpus, from todotango.

Anthony, 2026-10-16: "We can download the lyrics", and then "This is scholarship, not commercial work, and
clearly under fair use." His library, his machine, his call. The distinction this tool keeps is not about fair
use at all, it is about plumbing: everything here lands in ~/corpus/texts, which is OUTSIDE every repository,
because the atlas repo mirrors to public GitHub and writing a lyric into it would be publishing rather than
copying. The works lists in dossiers/ still only NAME a tango; the text lives here.

Why todotango and not the Internet Archive: the corpus fetcher knows the Archive and Gutenberg because that is
where out-of-copyright books are. Tango lyrics are not there. todotango is the standing archive for the form,
with the texts, the authorship and the discographies together.

The site is ASP.NET, which shapes the whole tool:
  * /creadores/ has no alphabetical index and no query-string search. It searches by POSTBACK, so a lookup means
    fetching the page, carrying __VIEWSTATE / __VIEWSTATEGENERATOR / __EVENTVALIDATION forward, and posting the
    search box with the button's event target. Guessing a creator id is not possible and not attempted.
  * A song lives at /musica/tema/<id>/<Title-Slug>/ and the lyric is the longest run of <br>-separated text on
    it. There is no lyric container to select: the ids on the page (main_Tema1_DL_OtrasLetras_hl_Letra_N) are
    links to OTHER songs' lyrics, not this one's. Verified against "La sulamita", whose longest block is the
    verse beginning "Fue en El Cairo, por primera vez la vi".

Politeness: one request a second, a real User-Agent naming the project, and resumable -- a song already on disk
is never refetched. robots.txt returns 404, so nothing is disallowed, which is not a licence to hammer it.

    python3 atlas_tools/corpus_lyrics.py --find "Carlos Gardel"
    python3 atlas_tools/corpus_lyrics.py --slug carlos_gardel --creator 1
    python3 atlas_tools/corpus_lyrics.py --slug carlos_gardel --creator 1 --limit 20
"""
import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.todotango.com"
UA = "atlas-corpus/0.1 (private research corpus for the Atlas of Journeys; run from nodus)"
# Alongside the books, not in a tree of their own: Anthony, 2026-10-16, "Yes you can have a lyrics alongside
# books". So a subject's folder under ~/corpus/files holds everything of theirs, whatever its form, which is the
# same refusal to sort by medium that the works lists make. The manifest is separately named because
# corpus_fetch.py already owns manifest.json in that folder and the two must not clobber each other.
TEXTS = Path(os.path.expanduser("~/corpus/files"))
MANIFEST = "lyrics_manifest.json"
PAUSE = 1.0


def fetch(url, data=None, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA,
                **({"Content-Type": "application/x-www-form-urlencoded"} if data else {})})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"{url}: {last!r}")


def hidden_fields(page):
    out = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(r'id="%s"[^>]*value="([^"]*)"' % name, page)
        if m:
            out[name] = htmlmod.unescape(m.group(1))
    return out


def find_creator(name):
    """[(id, slug)] for a creator name, via the site's own postback search."""
    page = fetch(BASE + "/creadores/")
    time.sleep(PAUSE)
    fields = hidden_fields(page)
    fields.update({"__EVENTTARGET": "ctl00$Barranav1$btn_Buscar", "__EVENTARGUMENT": "",
                   "ctl00$Barranav1$tb_Buscar": name})
    res = fetch(BASE + "/creadores/", data=urllib.parse.urlencode(fields).encode())
    time.sleep(PAUSE)
    hits = re.findall(r'href="[^"]*creadores/ficha/(\d+)/([^"/]+)', res)
    seen, out = set(), []
    for cid, slug in hits:
        if cid not in seen:
            seen.add(cid)
            out.append((cid, slug))
    return out, res


def creator_temas(cid, slug):
    """[(tema id, title slug)] linked from a creator's page.

    The name slug is REQUIRED: /creadores/ficha/41/ is a 404, only /creadores/ficha/41/Enrique-Santos-Discepolo
    resolves. The id alone is not an address on this site, which is why --find prints both.
    """
    url = f"{BASE}/creadores/ficha/{cid}/{slug}"
    page = fetch(url)
    time.sleep(PAUSE)
    hits = re.findall(r'href="[^"]*musica/tema/(\d+)/([^"/]+)', page)
    seen, out = set(), []
    for tid, title in hits:
        if tid not in seen:
            seen.add(tid)
            out.append((tid, title))
    return out


def lyric_of(tid, title):
    """The lyric text of one song, or None. The longest <br>-separated block: see the note above on why there
    is no container to select."""
    url = f"{BASE}/musica/tema/{tid}/{title}/"
    page = fetch(url)
    best = ""
    for b in re.findall(r"<div[^>]*>(.{200,8000}?)</div>", page, re.S):
        if b.count("<br") < 6:
            continue
        txt = re.sub(r"<br\s*/?>", "\n", b)
        txt = re.sub(r"<[^>]+>", "", txt)
        txt = htmlmod.unescape(txt)
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
        if len(txt) > len(best):
            best = txt
    return (best or None), url


def safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:90]


def main():
    args = sys.argv[1:]
    if "--find" in args:
        name = args[args.index("--find") + 1]
        hits, _ = find_creator(name)
        if not hits:
            print(f"no creator found for {name!r}")
            return
        for cid, slug in hits[:20]:
            print("  id=%-7s %s" % (cid, slug))
        return

    slug = args[args.index("--slug") + 1]
    # --creator takes "<id>/<Name-Slug>" exactly as --find prints it, because the id alone 404s
    cref = args[args.index("--creator") + 1]
    if "/" not in cref:
        raise SystemExit("--creator needs <id>/<Name-Slug>, e.g. 41/Enrique-Santos-Discepolo "
                         "(run --find first; the bare id is not an address on this site)")
    cid, cslug = cref.split("/", 1)
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 6

    temas = creator_temas(cid, cslug)
    print(f"{slug}: creator {cid} links {len(temas)} songs", flush=True)
    out_dir = TEXTS / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    mpath = out_dir / MANIFEST
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    got = 0
    for tid, title in temas[:limit]:
        if tid in manifest and manifest[tid].get("chars"):
            continue
        try:
            text, url = lyric_of(tid, title)
        except Exception as e:
            manifest[tid] = {"error": repr(e)}
            time.sleep(PAUSE)
            continue
        if not text or len(text) < 120:
            manifest[tid] = {"title": title, "url": url, "no_lyric": True}
            time.sleep(PAUSE)
            continue
        dest = out_dir / f"{tid}_{safe(title)}.txt"
        header = (f"# {title.replace('-', ' ')}\n# source: {url}\n"
                  f"# retrieved: {time.strftime('%Y-%m-%d')}\n"
                  f"# private research copy, not for redistribution\n\n")
        dest.write_text(header + text + "\n", encoding="utf-8")
        manifest[tid] = {"title": title, "url": url, "file": dest.name, "chars": len(text)}
        got += 1
        if got % 10 == 0:
            print(f"  {got} lyrics", flush=True)
        time.sleep(PAUSE)
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{slug}: {got} new lyrics, {len(manifest)} songs seen -> {out_dir}")


if __name__ == "__main__":
    main()
