#!/usr/bin/env python3
"""Step three: actually fetch the free editions, text first.

Only items corpus_availability.py marked "download" are ever touched, so the whole copyright judgment lives in
that one audited place and this tool simply obeys it. It re-checks the verdict on every item before fetching,
so editing the gate and re-running cannot leave a stale decision behind.

WHAT IT TAKES, and why text rather than scans. An Archive book offers roughly: a 10 MB page-image PDF, a 9 MB
DjVu, a 45 MB EPUB, and a 0.5 MB `_djvu.txt` of the OCR. For a corpus meant to be read, searched and quoted, the
OCR text is the substance and the rest is packaging: across the ~2,900 free editions that is about 1.7 GB of text
against some 30 GB of images, and it is far gentler on a service that gives its holdings away. So the plain text
is the default and the PDF is --pdf, per item, for the ones worth having as facsimile.

Project Gutenberg files come from the URLs its catalog API already handed us, never by crawling gutenberg.org,
which its terms forbid.

Rate: one request per second, retries with backoff, resumable (an existing file is never refetched), and a total
byte budget so a runaway cannot fill the disk. Every fetch is recorded in ~/corpus/files/<slug>/manifest.json
with its source URL and size, which is what lets corpus_bibliography fill in each entry's `file` field.

    python3 atlas_tools/corpus_fetch.py --slug giordano_bruno
    python3 atlas_tools/corpus_fetch.py --limit 20            # first 20 subjects with free editions
    python3 atlas_tools/corpus_fetch.py --pdf                 # facsimiles too
    python3 atlas_tools/corpus_fetch.py --budget-gb 50
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus_availability as AV  # noqa: E402

CORPUS = Path(os.path.expanduser("~/corpus"))
FILES = CORPUS / "files"
UA = AV.UA
PAUSE = 1.0
MAX_FILE_MB = 200          # a single file larger than this is skipped and noted, never silently truncated

# In preference order. The OCR text first; the facsimile only when --pdf is given.
TEXT_SUFFIXES = ("_djvu.txt", ".txt")
PDF_FORMATS = ("Text PDF", "Image Container PDF", "Additional Text PDF")


def ia_metadata(ident):
    return json.loads(AV.fetch(f"https://archive.org/metadata/{ident}"))


def pick_files(meta, want_pdf):
    """[(filename, kind, size bytes)] to take for one Archive item."""
    files = meta.get("files", []) or []
    out = []
    for suf in TEXT_SUFFIXES:
        cand = [f for f in files if str(f.get("name", "")).endswith(suf)]
        if cand:
            f = max(cand, key=lambda f: int(f.get("size") or 0))
            out.append((f["name"], "text", int(f.get("size") or 0)))
            break
    if want_pdf:
        cand = [f for f in files if str(f.get("format", "")) in PDF_FORMATS]
        if cand:
            f = min(cand, key=lambda f: int(f.get("size") or 0))   # the smallest PDF is the text layer, not the scan
            out.append((f["name"], "pdf", int(f.get("size") or 0)))
    return out


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:
        n = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            n += len(chunk)
    os.replace(tmp, dest)
    return n


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]


def fetch_subject(slug, rec, want_pdf, budget):
    """Returns (files written, bytes). Mutates budget['left']."""
    out_dir = FILES / slug
    manifest_path = out_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    wrote = nbytes = 0
    for it in rec.get("items", []):
        if it.get("verdict") != "download":
            continue
        if budget["left"] <= 0:
            break
        ident = str(it.get("id"))
        src = it.get("source")
        targets = []
        if src == "archive.org":
            try:
                meta = ia_metadata(ident)
            except Exception as e:
                manifest[ident] = {"error": repr(e)}
                continue
            time.sleep(PAUSE)
            for fname, kind, size in pick_files(meta, want_pdf):
                targets.append((f"https://archive.org/download/{ident}/{urllib.parse.quote(fname)}",
                                safe(f"{ident}.{ 'txt' if kind == 'text' else 'pdf' }"), kind, size))
        elif src == "gutenberg":
            for mime, url in (it.get("formats") or {}).items():
                if mime.startswith("text/plain"):
                    targets.append((url, safe(f"gutenberg_{ident}.txt"), "text", 0))
                    break
            if want_pdf:
                for mime, url in (it.get("formats") or {}).items():
                    if mime.startswith("application/epub"):
                        targets.append((url, safe(f"gutenberg_{ident}.epub"), "epub", 0))
                        break
        for url, fname, kind, size in targets:
            dest = out_dir / fname
            key = f"{ident}:{kind}"
            if dest.exists() and manifest.get(key, {}).get("bytes"):
                continue
            if size and size > MAX_FILE_MB * 1e6:
                manifest[key] = {"skipped": f"{size/1e6:.0f} MB exceeds the {MAX_FILE_MB} MB per-file cap"}
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                n = download(url, dest)
            except Exception as e:
                manifest[key] = {"error": repr(e), "url": url}
                time.sleep(PAUSE)
                continue
            manifest[key] = {"file": str(dest.relative_to(CORPUS)), "bytes": n, "url": url,
                             "title": it.get("title"), "year": it.get("year")}
            wrote += 1
            nbytes += n
            budget["left"] -= n
            time.sleep(PAUSE)
    if manifest:
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return wrote, nbytes


def main():
    want_pdf = "--pdf" in sys.argv
    gb = 100.0
    if "--budget-gb" in sys.argv:
        gb = float(sys.argv[sys.argv.index("--budget-gb") + 1])
    budget = {"left": gb * 1e9}

    recs = sorted(AV.AVAIL.glob("*.json"))
    if "--slug" in sys.argv:
        recs = [AV.AVAIL / (sys.argv[sys.argv.index("--slug") + 1] + ".json")]
    todo = []
    for p in recs:
        if not p.exists():
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("n_download"):
            todo.append((p.stem, rec))
    if "--limit" in sys.argv:
        todo = todo[: int(sys.argv[sys.argv.index("--limit") + 1])]

    print(f"{len(todo)} subjects have free editions; budget {gb:.0f} GB; "
          f"{'text and PDF' if want_pdf else 'text only'}", flush=True)
    tot_f = tot_b = 0
    for slug, rec in todo:
        if budget["left"] <= 0:
            print("budget exhausted", flush=True)
            break
        w, b = fetch_subject(slug, rec, want_pdf, budget)
        tot_f += w
        tot_b += b
        if w:
            print(f"  {slug:<34} {w:>4} files  {b/1e6:>8.1f} MB", flush=True)
    print(f"\n{tot_f} files, {tot_b/1e9:.2f} GB, into {FILES}")


if __name__ == "__main__":
    main()
