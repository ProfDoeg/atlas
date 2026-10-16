#!/usr/bin/env python3
"""What did the atlas write? An inventory of every work by every subject, read out of the dossiers.

Anthony, 2026-10-13: "I would like to start downloading all the books and articles and letters written by each
person in the atlas ... Let's do it on nodus."

Downloading is step two. This is step one, and it is deliberately offline: 890 dossiers are already on disk and
869 of them carry a "## Works by <Name>" section that the Codex machine researched. Reading those costs nothing,
touches no remote host, and answers the questions that decide the shape of the whole project before a single byte
is fetched -- how many works there are, how many subjects wrote anything at all, how many are old enough to be
out of copyright anywhere, and which subjects the dossiers cannot help with.

What it extracts, per bulleted line of a works section:

  * the "### " subsection it sits under, verbatim, as the kind ("Letters", "Plato translations and commentaries",
    "Original philosophical and theological works"). The dossiers group works their own way and that grouping is
    information; it is not flattened into a guessed book/article/letter trichotomy.
  * the leading bold date clause, verbatim, because it is rarely a bare year: "1469-1474; printed 1482",
    "Approximately 1474; first Latin printing 1476", "After May 1498", "Vernacular adaptation, date debated".
  * every italicised title on the line. A line often carries two, the Latin and the vernacular, or a title and
    its alternative ("*Di Dio et anima* / *Compendium de opinionibus...*"); both are kept, the first as the
    title and the rest as alternates, because either may be what a library catalogues it under.
  * a year, parsed from the date clause only where a four-digit year is actually present, for the copyright
    triage below. No year is invented.

What it does NOT do: decide whether a work is downloadable. That needs the network and is the next tool. It does
sort subjects into a crude PUBLIC-DOMAIN-ANYWHERE bucket (every dated work before 1800) and a NEEDS-CHECKING
bucket, so the pilot can start on the half of the atlas where the answer is not in doubt.

    python3 atlas_tools/corpus_inventory.py                 # writes ~/corpus/inventory.jsonl and prints a summary
    python3 atlas_tools/corpus_inventory.py --slug marsilio_ficino    # one subject, to the screen
"""
import csv
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATLAS = HERE.parent
DOSSIERS = ATLAS / "dossiers"
CATALOG = ATLAS / "catalog_subjects.csv"
OUT_DIR = Path(os.path.expanduser("~/corpus"))
OUT = OUT_DIR / "inventory.jsonl"

# A title in italics, not bold: *Title*, never **date**.
ITALIC = re.compile(r"(?<!\*)\*([^*\n]{2,200})\*(?!\*)")
# The bold clause that opens most work lines: "- **1489:** ..." or "- **Late works:** ..."
LEAD_BOLD = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*:?\s*")
YEAR = re.compile(r"\b(\d{3,4})\b")
WORKS_H2 = re.compile(r"^##\s+Works\b", re.I)
ANY_H2 = re.compile(r"^##\s+")
H3 = re.compile(r"^###\s+(.*)")


def travelers():
    """slug -> (traveler, death year or None). The death year, not the work's date, is what decides copyright:
    the dossiers date only 697 of 11,405 titles, mostly because a medieval Arabic or Sanskrit title simply has no
    attached year, while the catalog's `years` field gives a lifespan for almost every built subject. A subject
    long dead is out of copyright everywhere regardless of when any one work is dated."""
    out = {}
    if CATALOG.exists():
        with open(CATALOG, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out[r["slug"]] = (r["traveler"], death_year(r.get("years", "")))
    return out


def death_year(years):
    """The later year of a lifespan string, None when it is BCE, open, or absent. '1433-1499' -> 1499;
    'c. 1813-1638 BC' -> None (BCE, and anyway far out of copyright); '1889-' -> None (no death recorded)."""
    if not years or re.search(r"\bBCE?\b|a\.?C\.?", years):
        return None
    ys = [int(y) for y in re.findall(r"\b(\d{3,4})\b", years) if 100 <= int(y) <= 2100]
    return max(ys) if ys else None


def works_section(text):
    """The lines of the '## Works by ...' section, or [] if the dossier has none."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if WORKS_H2.match(ln):
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for ln in lines[start:]:
        if ANY_H2.match(ln):
            break
        out.append(ln)
    return out


DATEISH = re.compile(r"\b(c|ca|circa|before|after|early|late|mid|approx\w*|undated|posthum\w*|"
                     r"published|printed|written|composed|various|date|dates|unknown|century|BCE?|AD)\b", re.I)


def looks_like_date(s):
    """Is this leading bold clause a DATE or a TITLE?

    Work lines open with bold either way: "**1489:** *De vita libri tres*" but also
    "**2 Thessalonians:** divided opinion". Treating every bold opener as a date lost the second kind entirely.
    A 3-4 digit run means a year; a single digit does not, which is what keeps "2 Thessalonians" and
    "1 Timothy, 2 Timothy, Titus" on the title side.
    """
    return bool(re.search(r"\d{3,4}", s)) or bool(DATEISH.search(s))


def table_cells(line):
    """(title, rest) for one markdown table row, or None for a separator, a header, or a non-row.

    Works given as a table rather than a list. Paul's seven undisputed letters are a table with columns
    Work / Greek title / date / notes, and so are many musical and architectural catalogues; reading only
    bullets made those subjects look as though they had written nothing at all.
    """
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    cells = [c.strip() for c in s.strip("|").split("|")]
    if not cells or not cells[0]:
        return None
    if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
        return None
    title = re.sub(r"\*+", "", cells[0]).strip()
    if not title or looks_like_date(title):
        return None
    return title, " · ".join(c for c in cells[1:] if c)


def parse(slug, text):
    rows, kind = [], ""
    sec = works_section(text)
    for ln in sec:
        h = H3.match(ln)
        if h:
            kind = h.group(1).strip()
            continue
        if ln.strip().startswith("|"):
            # Parsed inline, not in a second pass, so each row keeps the "###" heading it actually sits under.
            # A separate pass gave Paul's seven undisputed letters the kind "Speeches", the last heading in his
            # section, because by then the walk had finished.
            tc = table_cells(ln)
            if tc:
                title, rest = tc
                hdr = {"work", "title", "obra", "título", "titulo"}
                if title.lower() in hdr or any(h in title.lower() for h in ("greek title", "approximate date")):
                    continue                          # the table's own header row
                ys = [int(y) for y in YEAR.findall(rest) if 100 <= int(y) <= 2100]
                rows.append({"slug": slug, "kind": kind, "date_text": rest[:160],
                             "year": min(ys) if ys else None, "title": title, "alt_titles": [], "note": ""})
            continue
        if not re.match(r"^\s*[-*]\s+", ln):
            continue
        body = ln
        m = LEAD_BOLD.match(ln)
        date_text, bold_title = "", ""
        if m:
            lead = m.group(1).strip().rstrip(":")
            if looks_like_date(lead):
                date_text = lead
            else:
                bold_title = lead
            body = ln[m.end():]
        titles = [t.strip() for t in ITALIC.findall(body)]
        titles = [t for t in titles if not t.startswith("(")]
        if not titles and bold_title:
            titles = [bold_title]                     # "**2 Thessalonians:** divided opinion"
        elif bold_title:
            titles = [bold_title] + titles
        ys = [int(y) for y in YEAR.findall(date_text) if 100 <= int(y) <= 2100]
        rows.append({
            "slug": slug,
            "kind": kind,
            "date_text": date_text,
            "year": min(ys) if ys else None,
            "title": titles[0] if titles else "",
            "alt_titles": titles[1:],
            # A line with no title at all is still a real statement about the corpus ("Numerous short treatises,
            # prayers, orations ... gathered only in the Opera omnia"). Keep its prose so nothing is silently lost.
            "note": "" if titles else re.sub(r"\s+", " ", body).strip(),
        })
    return rows


def main():
    names = travelers()
    files = sorted(DOSSIERS.glob("*.dossier.md"))
    if "--slug" in sys.argv:
        want = sys.argv[sys.argv.index("--slug") + 1]
        files = [DOSSIERS / f"{want}.dossier.md"]
    all_rows, no_section, no_works = [], [], []
    for p in files:
        slug = p.name[: -len(".dossier.md")]
        text = p.read_text(encoding="utf-8", errors="replace")
        # A dossier researched as a biography often lists no works at all: Aby Warburg's has no Works section,
        # though the Mnemosyne atlas is the thing he is remembered for and his own journey file dates its
        # beginning to 1924. Rather than rewrite Codex's output, a focused bibliography pass may drop a
        # dossiers/<slug>.works.md beside it, in the same "## Works by" shape, and it is read here as well.
        extra = DOSSIERS / f"{slug}.works.md"
        if extra.exists():
            text = text + "\n\n" + extra.read_text(encoding="utf-8", errors="replace")
        if not works_section(text):
            no_section.append(slug)
            continue
        rows = parse(slug, text)
        if not rows:
            no_works.append(slug)
        tr, dy = names.get(slug, ("", None))
        for r in rows:
            r["traveler"] = tr
            r["death_year"] = dy
        all_rows += rows

    if "--slug" in sys.argv:
        for r in all_rows:
            print(json.dumps(r, ensure_ascii=False))
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    titled = [r for r in all_rows if r["title"]]
    subjects = {r["slug"] for r in all_rows}
    dated = [r for r in titled if r["year"]]
    pre1800 = [r for r in dated if r["year"] < 1800]
    pre1930 = [r for r in dated if r["year"] < 1930]
    by_subject = {}
    for r in titled:
        by_subject.setdefault(r["slug"], []).append(r)
    # Triage by the author's death, the rule every jurisdiction actually uses. 1900 is deliberately
    # conservative: life+70 clears 1956, life+80 clears 1946, so a subject dead by 1900 is out of copyright
    # under any regime on earth, with no edition-by-edition argument to have.
    dy_of = {s: (rs[0].get("death_year")) for s, rs in by_subject.items()}
    clear = sorted(s for s, dy in dy_of.items() if dy and dy < 1900)
    modern = sorted(s for s, dy in dy_of.items() if dy and dy >= 1900)
    undated = sorted(s for s, dy in dy_of.items() if not dy)

    print(f"dossiers read                     {len(files)}")
    print(f"  with a Works section            {len(files) - len(no_section)}")
    print(f"  without one                     {len(no_section)}")
    print(f"  section present but empty       {len(no_works)}")
    print(f"work lines                        {len(all_rows)}")
    print(f"  with an italicised title        {len(titled)}")
    print(f"  prose-only (no discrete title)  {len(all_rows) - len(titled)}")
    print(f"subjects with at least one work   {len(subjects)}")
    print(f"titles carrying a parsed year     {len(dated)}")
    print(f"  before 1800                     {len(pre1800)}")
    print(f"  before 1930                     {len(pre1930)}")
    print(f"\nby the author's death year, which is what copyright turns on:")
    print(f"  subjects dead before 1900 (free everywhere)   {len(clear)}  "
          f"({sum(len(by_subject[s]) for s in clear)} titles)")
    print(f"  died 1900 or later (check each)               {len(modern)}  "
          f"({sum(len(by_subject[s]) for s in modern)} titles)")
    print(f"  no death year (BCE, legendary, or living)     {len(undated)}  "
          f"({sum(len(by_subject[s]) for s in undated)} titles)")
    print(f"\nwrote {OUT}")
    if no_section:
        print(f"\nno Works section ({len(no_section)}): " + ", ".join(no_section[:25])
              + (" ..." if len(no_section) > 25 else ""))


if __name__ == "__main__":
    main()
