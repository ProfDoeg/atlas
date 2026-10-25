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
# Any bold span, anywhere. Prose names a title in bold as readily as in italics, and triple-starred
# ***Der Leuchter*** is bold-plus-italic, so the inner stars are stripped by the caller.
#   "**plain bold**", "***bold italic***", and the irregular shape the works files actually use for an editor's
# volume: "***Schöpferische Erkenntnis* (1922)**" -- bold wrapping an italic title plus its year, so the inner
# asterisks are UNBALANCED. Terminating on a run of two or more stars steps over the stray single one, which a
# [^*] content class cannot do: it failed to match at all, and the next attempt then captured the prose BETWEEN
# two titles (", subtitled an introduction to the School of Wisdom, and") as if that were a title.
BOLD = re.compile(r"\*{2,3}(.{2,200}?)\*{2,3}")
ITALIC_ONLY = re.compile(r"(?<!\*)\*([^*\n]{2,200})\*(?!\*)")
# A year in parentheses or trailing, as prose writes it inside a bold title:
# "**Das Reisetagebuch eines Philosophen (1919)**", "**Das Spektrum Europas / Europe (1928)**".
TRAILING_YEAR = re.compile(r"[\s,;(\[]*\b(1[0-9]{3}|20[0-9]{2}|[1-9][0-9]{2})\b"
                           r"(?:\s*[-–/]\s*(?:c\.?\s*)?[0-9]{2,4})?[\s)\].,;]*$")
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
    """The lines of EVERY '## Works ...' section in the text, concatenated, or [] if there are none.

    Every, not the first. A dossiers/<slug>.works.md is appended to the end of the dossier before parsing, so
    when the dossier already carries a thin or empty works section of its own, taking only the first match
    silently discarded the researched one: al-Kindi's 295 entries parsed as 6. The nine subjects staged before
    this was noticed happened to have no dossier section at all, which is why they worked and hid the bug.
    """
    lines = text.splitlines()
    out, inside = [], False
    for ln in lines:
        if WORKS_H2.match(ln):
            inside = True
            continue
        if ANY_H2.match(ln):
            inside = False
            continue
        if inside:
            out.append(ln)
    return out


DATEISH = re.compile(r"\b(c|ca|circa|before|after|early|late|mid|approx\w*|undated|posthum\w*|"
                     r"published|printed|written|composed|various|date|dates|unknown|century|BCE?|AD)\b", re.I)

# The same words, split by how safely each one identifies a DATE rather than appearing inside a title.
# STRONG words are chronological apparatus and effectively never occur in a title, so they settle the question
# at any length: "c. 54 CE, or as early as c. 49-50" is a date however many words long it is. WEAK words are
# ordinary English that titles use freely -- Bacon's "A Declaration ... of Robert, late Earl of Essex" was read
# as a date because of "late", and the work was lost -- so they only count in a lead short enough to be a date
# clause rather than a sentence.
DATE_STRONG = re.compile(r"\b(c|ca|circa|approx\w*|undated|posthum\w*|century|centuries|BCE?|CE|AD|"
                         r"floruit|fl)\b\.?", re.I)
DATE_WEAK = re.compile(r"\b(before|after|early|late|mid|published|printed|written|composed|various|"
                       r"date|dates|unknown)\b", re.I)
# A day-and-month lead, which a discography or a diary uses as its organising key: Ada Falcon's recordings are
# itemised "- **2 May**: ..." and "2 May" became a work of hers, as did "4 May", "19 March" for Magellan and
# "14 November" for Guido Keller. A month name with nothing but a day number around it is a date.
# What a date clause leaves behind once its year is removed: "**About 1872:**" -> "About", "**From 1850**" ->
# "From". Albert Pike's file contributed ten works called "about" this way, Adriano's nine called "About".
DATE_RESIDUE = {"about", "around", "roughly", "approximately", "from", "by", "to", "between", "during",
                "until", "till", "before", "after", "since", "in", "on", "at", "of", "and", "or", "the",
                "early", "late", "mid", "circa", "published", "printed", "written", "composed", "undated",
                "various", "unknown", "onward", "onwards", "ff", "later", "earlier",
                # Hedges and status words a dated lead hangs on: "**Probably 1580:**", "**unfinished,
                # 1623**", "**traditionally c. 300 BCE**". Left in, these were the single largest source of
                # false transmission edges -- "Probably" alone wired 164 pairs of people together, because a
                # shared title is how that graph claims two men read the same book.
                "probably", "possibly", "perhaps", "traditionally", "conventionally", "reportedly",
                "allegedly", "uncertain", "disputed", "doubtful", "attributed", "unfinished", "incomplete",
                "fragment", "fragments", "fragmentary", "lost", "extant", "surviving", "undetermined",
                "publication", "importance", "testament", "epistolario", "epistolary",
                "principally", "chiefly", "mainly", "mostly", "largely", "unrealized", "unrealised",
                "childhood", "youth", "adulthood", "throughout", "spring", "summer", "autumn", "fall",
                "winter"}

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DAY_MONTH = re.compile(r"^\s*(?:[0-9]{1,2}\s*(?:st|nd|rd|th)?[\s.]*)?"
                       + MONTH +
                       # A month RANGE is just as much a date: "July-August", "February-March" and the rest
                       # were works of their subjects, and each range wired together everyone whose
                       # bibliography happened to use the same two months.
                       r"(?:\s*[-–—/to]+\s*" + MONTH + r")?"
                       r"(?:[\s.]*[0-9]{1,2}(?:st|nd|rd|th)?)?\s*$", re.I)


# Bold leads that are FIELD NAMES, not titles. A dossier describing one work often itemises it as
# "- **Original language:** Hebrew" / "- **Structure:** 48 chapters", and reading those as titles invented
# works called "Original language" and "Structure" -- which then wired Ezekiel to Braille, Hallaj and Simon
# Magus by "shared work", since every such dossier has the same fields.
SOURCE_HEADINGS = {"sources", "source", "bibliography", "references", "further reading", "notes on sources",
                   "selected bibliography", "works consulted", "fuentes"}

ATTR_LABELS = {"original language", "language", "structure", "traditional attribution", "attribution",
               "authorship", "author", "date", "dating", "genre", "form", "length", "status", "manuscript",
               "manuscripts", "transmission", "canonicity", "title", "titles", "contents", "summary",
               "theme", "themes", "style", "setting", "sources", "source", "editions", "edition",
               "translations", "translation", "recension", "recensions", "provenance", "medium",
               "materials", "dimensions", "location", "collection", "scope", "note", "notes",
               # Table and field labels that reach the prose pass as bold spans rather than as a header row:
               # Court de Gebelin's file contributed thirteen works called "Type" and one called "Pages".
               "type", "types", "pages", "page", "volume", "volumes", "number", "no", "issue", "year",
               "years", "publisher", "place", "city", "format", "extent", "size", "series", "part", "parts",
               "chapter", "chapters", "section", "sections", "folio", "folios", "shelfmark", "call number",
               "identifier", "total", "count", "subject", "keywords", "category", "kind", "work", "works",
               "publication", "importance", "significance", "reception", "influence", "context",
               "title in english", "english title", "latin title", "hebrew title", "arabic title", "greek title"}


def looks_like_attribute(s):
    """Is this bold lead a field name rather than a work's title?

    Two tests, because neither alone is enough. The explicit list catches the recurring dossier fields. The
    second catches the open-ended rest: a title carries a capitalised word somewhere past its first word
    ("2 Thessalonians", "De vita libri tres"), while a field name is ordinary lowercase language after its
    initial capital ("Original language", "Traditional attribution").
    """
    t = s.strip().rstrip(":").strip()
    if t.lower() in ATTR_LABELS:
        return True
    words = t.split()
    if 2 <= len(words) <= 3 and not any(w[:1].isupper() for w in words[1:]):
        return True
    return False


# Emphasised spans in PROSE that are not works. Prose uses bold and italic for more than titles: for a coined
# concept ("**Gana**", Keyserling's telluric impulse), for a foreign phrase, for a motto, for plain stress.
# A span is rejected when it is clearly one of those rather than something made.
# A single capitalised word is deliberately NOT rejected, though it is the ambiguous case: Keyserling's coined
# "Gana" and Bacon's "Essays" are indistinguishable by shape. The costs are not symmetric. Dropping *Essays*
# loses the most-reprinted book Bacon wrote; keeping "Gana" adds a concept he minted, which under Anthony's
# own widening of the catalogue -- "creations, books and artworks…etc", obra and manifestation alongside book
# -- is arguably an entry rather than an error. So the rule errs toward keeping, and every prose-derived row
# is stamped from="prose" so the decision stays visible and auditable instead of being buried in a count.
PROSE_NOT_WORKS = re.compile(
    r"^(?:"
    r"[a-z\W]*"                                  # all-lowercase stress: *not*, *is*, *only*
    r"|\d{1,4}(?:\s*[-–]\s*\d{1,4})?"            # a bare year or span
    r")$")

PROSE_STOP = {"the", "and", "or", "not", "sic", "ibid", "passim", "op cit", "circa", "idem",
              "see also", "above", "below", "ibidem", "et al", "cf"}


def clean_title(t):
    """Strip a title's trailing date, and the bracket that date was sitting in.

    "Das Buch vom Ursprung (published posthumously, 1947)" loses ", 1947)" to TRAILING_YEAR and is left holding
    an unclosed "(", so an unbalanced opening bracket is cut back with whatever follows it. The date is not
    lost: the caller reads the year off the same span before this runs.
    """
    # A final parenthetical CONTAINING a year is a date, however it is worded: "(1919 onward)",
    # "(1920-c.1942)", "(begun 1937, published 1948-1963)", "(published posthumously, 1947)". Matching the year
    # alone left "Der Leuchter (1919 onward)" looking like a date and lost the yearbook entirely.
    t = re.sub(r"\s*[(\[][^()\[\]]*\b(?:1[0-9]{3}|20[0-9]{2}|[1-9][0-9]{2})\b[^()\[\]]*[)\]]\s*$", "", t).strip()
    # A LEADING date, which is how a chronological bibliography writes its entries. Warburg's works file runs
    # "**1893 - "Sandro Botticellis Geburt der Venus"**" for every item, and keeping the prefix made each
    # title begin with its year -- unsortable, unmatchable against a library, and ugly in the catalogue. The
    # year is read off the span separately, so nothing is lost by cutting it here.
    # Accepted only if a TITLE is left behind. An ISO date, "1861-03-04", is year + separator + number all the
    # way down, so the strip ate "1861-03-" and left "04" -- which then became a work of Lincoln's, 25 times
    # over. A remnant that is bare digits, or too short to be a title, means the whole span was the date.
    lead_cut = re.sub(r"^(?:c\.?\s*|ca\.?\s*)?(?:1[0-9]{3}|20[0-9]{2}|[1-9][0-9]{2})"
                      r"(?:\s*[-–/]\s*(?:c\.?\s*)?[0-9]{2,4})?\s*[-–—:.,]\s*", "", t).strip()
    if lead_cut != t and len(lead_cut) >= 4 and not re.fullmatch(r"[\d\s./-]+", lead_cut):
        t = lead_cut
    t = TRAILING_YEAR.sub("", t).strip().rstrip(":,;.").strip()
    if t.count("(") > t.count(")"):
        t = t[: t.rfind("(")].strip().rstrip(",;:").strip()
    if t.count("[") > t.count("]"):
        t = t[: t.rfind("[")].strip().rstrip(",;:").strip()
    return t


def split_lead(lead):
    """A bold lead is a date, a title, or a title CARRYING its date. Return (date_text, title).

    The old rule was all-or-nothing: any year in the lead made the whole lead a date, so
    "- ***Der Leuchter* (1919 onward)** -- a yearbook" contributed a date of 1919 and no title at all, and the
    yearbook vanished. Keyserling lost Der Leuchter and Der Weg zur Vollendung exactly this way. Pulling the
    date off the end and keeping what remains recovers both without weakening the date test: a lead that is
    ONLY a date still has nothing left after the strip, and so is still read as a date.
    """
    lead = lead.replace("*", "").strip().rstrip(":").strip()
    body = clean_title(lead)
    if not body:                                  # "1489", "(1620)", "c. 1230" -- a date and nothing else
        return lead, ""
    # What is left of "About 1872" or "From 1850" is the preposition the date hung on, not a title. The test is
    # length as well as vocabulary: one or two function words is residue, while "From Here to Eternity" is a
    # title that happens to start with one, and a word list alone would have thrown it away.
    # Split on dashes as well as spaces: a season or life-stage range arrives as a single token,
    # "Spring-Summer" or "childhood-", so splitting on whitespace alone left it unrecognised and standing in
    # the catalogue as a work -- and then, being a title two people shared, as a transmission edge between them.
    words = [w for w in re.split(r"[\s/\-–—]+", body.strip(".,;:")) if w]
    if len(words) <= 2 and all(w.lower() in DATE_RESIDUE for w in words):
        return lead, ""
    if looks_like_date(body) or looks_like_attribute(body):
        return lead, ""
    # A year came off the end, so the lead was "Title (year)": keep both halves rather than either alone.
    return (lead if body != lead else ""), body


def prose_titles(body):
    """Emphasised titles from a PROSE line inside a Works section.

    The parser used to discard every line that was not a list item or a table row, and a great deal of the
    research is written as paragraphs. Francis Bacon's file names about seventeen works -- Novum Organum, the
    three Essays editions, the Advancement, De Augmentis, Sylva Sylvarum, New Atlantis, Henry VII, Valerius
    Terminus -- and ten were counted, because the rest sit in prose. Keyserling's file names fourteen and ONE
    was counted. The thin-bibliography audit was therefore partly measuring this function's absence rather than
    any gap in the research.

    Prose writes a title with its date inside the emphasis -- "**Das Reisetagebuch eines Philosophen / The
    Travel Diary of a Philosopher (1919)**" -- so the year is stripped off the span and kept rather than used to
    disqualify it. Rejecting any span containing a year, which is the right rule for a list's bold lead, threw
    away exactly the major works: Keyserling's Reisetagebuch, his South American Meditations and his Spektrum
    Europas all went that way.
    """
    # Bold spans first, removing each from the line, so the italics pass sees only what bold did not claim.
    # Otherwise an italic title nested inside a bold span is harvested twice and the leftover halves of the
    # markup become spurious titles of their own.
    spans = BOLD.findall(body)
    rest = BOLD.sub(" ", body)
    spans += ITALIC_ONLY.findall(rest)

    out = []
    for raw in spans:
        t = raw.replace("*", "").strip().strip("_ ").strip()
        t = clean_title(t)
        if not t or len(t) < 4:
            continue
        if t.lower().rstrip("?") in PROSE_STOP:
            continue
        if PROSE_NOT_WORKS.match(t):
            continue
        if looks_like_attribute(t):
            continue
        if t not in out:
            out.append(t)
    return out


def looks_like_date(s):
    """Is this leading bold clause a DATE or a TITLE?

    Work lines open with bold either way: "**1489:** *De vita libri tres*" but also
    "**2 Thessalonians:** divided opinion". Treating every bold opener as a date lost the second kind entirely.
    A 3-4 digit run means a year; a single digit does not, which is what keeps "2 Thessalonians" and
    "1 Timothy, 2 Timothy, Titus" on the title side.

    The word test applies only to a SHORT lead. DATEISH holds ordinary words -- late, early, mid, written,
    printed, various -- that occur inside real titles: Bacon's "A Declaration of the Practices and Treasons
    attempted by Robert, late Earl of Essex" was classified as a date and dropped because it contains "late".
    A date clause is a few words at most, so past about eight words the words no longer mean a date, however
    date-like one of them looks.
    """
    if re.search(r"\d{3,4}", s):
        return True
    if DAY_MONTH.match(s.strip().rstrip(":")):
        return True
    if DATE_STRONG.search(s):
        return True
    return len(s.split()) <= 8 and bool(DATE_WEAK.search(s))


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
    # A two-column table is an ATTRIBUTE table -- "Original language | Hebrew", "Structure | 48 chapters" --
    # not a list of works, and reading its first column as titles invented works called "Original language",
    # "Traditional attribution" and "Structure", which then wired Ezekiel to Braille, Hallaj and Simon Magus
    # through a shared "work". A real works table carries at least a title and two facts about it: Paul's is
    # Work / Greek title / Date / Notes.
    if len(cells) < 3:
        return None
    title = re.sub(r"\*+", "", cells[0]).strip()
    if not title or looks_like_date(title):
        return None
    return title, " · ".join(c for c in cells[1:] if c)


def parse(slug, text):
    rows, kind = [], ""
    pending = [None]          # one table row held back, in case a |---| separator proves it was the header
    sec = works_section(text)
    for ln in sec:
        h = H3.match(ln)
        if h:
            kind = h.group(1).strip()
            # A works.md ends with "### Sources", which is a ### and therefore still INSIDE the "## Works"
            # section: its citations were being read as works, so "Encyclopaedia Judaica" became a work of
            # Moses de Leon, Aaron the Levite, Rashi and David Sassoon, and the shared-work rule then wired
            # those four together. A shared bibliography is not a shared work.
            if kind.strip().lower().rstrip(":") in SOURCE_HEADINGS:
                kind = "__sources__"
            continue
        if kind == "__sources__":
            continue
        if ln.strip().startswith("|"):
            # Parsed inline, not in a second pass, so each row keeps the "###" heading it actually sits under.
            # A separate pass gave Paul's seven undisputed letters the kind "Speeches", the last heading in his
            # section, because by then the walk had finished.
            #
            # The header row is identified STRUCTURALLY, by the |---| separator that follows it, not by guessing
            # at its words. Markdown puts the header first, so a parser reading rows in order emits it as a work
            # unless it holds one row back: that is how "Hebrew title" became a work of Abulafia's and "Forms" a
            # work of Ezekiel's, and why every table in every dossier was contributing a phantom.
            if re.fullmatch(r"\|[\s:|-]+\|", ln.strip()):
                pending[0] = None                     # the row before a separator was the header
                continue
            if pending[0] is not None:
                rows.append(pending[0])
            pending[0] = None
            tc = table_cells(ln)
            if tc:
                title, rest = tc
                ys = [int(y) for y in YEAR.findall(rest) if 100 <= int(y) <= 2100]
                pending[0] = {"slug": slug, "kind": kind, "date_text": rest[:160],
                              "year": min(ys) if ys else None, "title": title, "alt_titles": [], "note": ""}
            continue
        if pending[0] is not None:                    # the table ended without a separator following this row
            rows.append(pending[0])
            pending[0] = None
        if not re.match(r"^\s*[-*]\s+", ln):
            # PROSE. Not a list item, not a table row, not under "### Sources" -- a paragraph of the Works
            # section, which until now was dropped whole. Much of the research is written this way, so this is
            # where the undercount lived rather than in any gap in the research itself.
            if not ln.strip() or ln.strip().startswith("#"):
                continue
            pb = re.sub(r"\(\[[^\]]*\]\([^)]*\)\)", " ", ln)       # ([Author, *Title*](url)) -- a citation
            pb = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", pb)       # [text](url) -> text
            pb = re.sub(r"https?://\S+", " ", pb)
            pts = prose_titles(pb)
            if not pts:
                continue
            # A year is assigned by NEARNESS, not by taking the paragraph's earliest. Bacon's Instauration
            # paragraph names 1620, 1622 and 1623; the minimum dated all four of its works 1620, which is right
            # for Novum Organum and wrong for the two Historiae. The closest year token in the line is the one
            # the sentence was attaching to.
            yrs = [(m.start(), int(m.group(1))) for m in YEAR.finditer(pb)
                   if 100 <= int(m.group(1)) <= 2100]
            for t in pts:
                tys = [int(y) for y in YEAR.findall(t) if 100 <= int(y) <= 2100]
                if tys:
                    yr = tys[0]
                else:
                    at = pb.find(t)
                    yr = min(yrs, key=lambda p: abs(p[0] - at))[1] if (yrs and at >= 0) else None
                # Each prose title becomes its own row, since a paragraph routinely names several works and
                # collapsing them into one title plus alt_titles would hide all but the first from every count.
                rows.append({"slug": slug, "kind": kind, "from": "prose",
                             "date_text": str(yr) if yr else "",
                             "year": yr, "title": t, "alt_titles": [], "note": ""})
            continue
        body = ln
        m = LEAD_BOLD.match(ln)
        date_text, bold_title = "", ""
        if m:
            date_text, bold_title = split_lead(m.group(1))
            body = ln[m.end():]
        # Strip source citations before looking for titles. The works lists cite like
        # "([Scholem, *Encyclopaedia Judaica*](https://...))", and the italics inside a citation are the
        # SOURCE's name, not the subject's work: harvesting them made "Encyclopaedia Judaica" a work of Moses
        # de Leon, Rashi, Aaron the Levite and David Sassoon, and then wired those four together as sharing it.
        # A shared bibliography is not a shared work.
        body = re.sub(r"\(\[[^\]]*\]\([^)]*\)\)", " ", body)      # ([Author, *Title*](url))
        body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)      # [text](url) -> text
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
    if pending[0] is not None:                        # a table that ran to the end of the section
        rows.append(pending[0])
    return dedupe(rows)


def norm_title(t):
    """A title reduced to what is the same across a list entry and a paragraph mention."""
    t = re.sub(r"\(.*?\)", " ", t or "")                  # "(1620)", "(Of the Wisdom of the Ancients)"
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE).lower()
    t = re.sub(r"^(the|a|an|de|das|der|die|le|la|el|il)\s+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def dedupe(rows):
    """One row per work, now that prose and lists both contribute.

    Bacon's file names Novum Organum in the Instauration paragraph AND in the philosophy list; Keyserling's
    names the Reisetagebuch twice. Counting both doubled exactly the works that are best documented.

    The merge is deliberately narrow: at least one side must be PROSE. Deduping on the title alone, which is
    what I wrote first, cost 4,346 works -- Cirlot 288 to 167, Ada Falcon 229 to 114, Balanchine 394 to 285 --
    because a discography or a catalogue raisonne legitimately repeats a title across years: a tango recorded
    twice, a ballet staged again, a book reissued. Two LIST entries sharing a title are two records, and the
    list is where the research put its structure. Only a paragraph restating what a list already itemised is a
    duplicate.

    Years must also be compatible, since a prose mention of a title the list carries twice belongs to one of
    them, not to both.
    """
    out, seen = [], {}
    for r in rows:
        key = norm_title(r.get("title"))
        if not key:                                       # untitled note rows are statements, never duplicates
            out.append(r)
            continue
        prior = seen.get(key)
        mergeable = (prior is not None
                     and (prior.get("from") == "prose") != (r.get("from") == "prose")
                     and (not prior.get("year") or not r.get("year")
                          or prior["year"] == r["year"]))
        if not mergeable:
            seen.setdefault(key, r)
            out.append(r)
            continue
        if prior.get("from") == "prose":                   # the list row is richer; it supersedes the prose one
            r["year"] = r.get("year") or prior.get("year")
            r["date_text"] = r.get("date_text") or prior.get("date_text")
            out[out.index(prior)] = r
            seen[key] = r
        else:
            prior["year"] = prior.get("year") or r.get("year")
            prior["date_text"] = prior.get("date_text") or r.get("date_text")
    return out


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
