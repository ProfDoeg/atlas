#!/usr/bin/env python3
"""Shared language between subjects that the corpus as a whole does not express.

Anthony, 2026-10-22: "Given word token vectors representing the corpus of each subject, let's construct a metric
to discover shared language between subjects that is not globally expressed by the 888 subjects" -- and, before
that, the sharpening that makes it work: not pairs but "a group uses that nobody else uses".

THE METRIC. Treat each SUBJECT as one document. For a term t, let users(t) be the subjects who use it and
df(t) = |users(t)|. A term is INFORMATIVE when 2 <= df(t) <= DF_MAX: shared, and not the property of the whole
corpus. Each such term is evidence binding its users together, and the fewer its users the stronger it binds,
so it carries weight

    w(t) = 1 / (df(t) - 1)

which is 1 for a term used by exactly two subjects and falls away as the term spreads. The affinity of a pair is
the summed weight of the informative terms they share, divided by the geometric mean of how many informative
terms each has at all:

    affinity(A,B) = sum_t w(t) / sqrt(|T_A| * |T_B|)

The normaliser matters more than the weighting. Without it this measures who has the biggest library: a subject
with 300 books shares more rare words with everyone by sheer volume, and Lincoln would top every list.

THREE THINGS THAT WOULD OTHERWISE MAKE IT LIE, each handled rather than hoped away:

  OCR. These texts are machine-read scans and the rarest strings in them are misreads, not rare words. A term
  is only counted for a subject if it appears in at least MIN_FILES of that subject's files (or twice, when
  they have only one). A scanning error does not repeat across independently scanned books, which is also why
  Anthony's group framing is stronger than a pairwise one: noise cannot bind three people.

  LANGUAGE. Shared rare words occur within a language, so an unguarded run would mostly rediscover who wrote in
  Latin. Pairs are reported with a crude language profile so a reader can see when that is what they are looking
  at, and --same-language-only restricts to pairs whose dominant language agrees.

  ANTHOLOGIES. If the same edition sits in two subjects' folders they share everything. Files are fingerprinted
  and a file appearing under more than one subject is dropped from both.

VALIDATION, which is the part that makes this evidence rather than a word game: the atlas already holds 12,868
documented connections. The run reports how far the top-ranked pairs beat chance at recovering them. If it does
not beat chance it is a frequency toy and should be said so.

    python3 atlas_tools/corpus_shared_language.py --limit 60      # a quick pass over 60 subjects
    python3 atlas_tools/corpus_shared_language.py                 # everyone with text
"""
import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CORPUS = Path(os.path.expanduser("~/corpus"))
FILES = CORPUS / "files"
ATLAS = Path(__file__).resolve().parent.parent
OUT = CORPUS / "shared_language.json"

DF_MAX = 8                 # a term used by more than this many subjects is not evidence of a circle
MIN_FILES = 2              # a term must appear in this many of a subject's files to count (OCR guard)
MIN_LEN, MAX_LEN = 5, 28
TOP_PAIRS = 60
MAX_BYTES = 4_000_000      # per file, so one enormous scan cannot dominate a subject

WORD = re.compile(r"[a-zà-öø-ÿ]{%d,%d}" % (MIN_LEN, MAX_LEN))
# Function words of the corpus's main languages. Not a stopword list for meaning -- these are simply words no
# rarity measure should ever see, and leaving them in wastes the df budget.
COMMON = set("""their there these those which would should could about after before where while among
against through between because another himself herself themselves without within during however
therefore nothing something everything nobody somebody anything whatever whenever wherever
dieser diesen welche werden wurden haben hatten nicht auch noch schon immer durch gegen ohne
aquel aquella quien cuando donde porque pero aunque desde hasta entre sobre tambien
celui celle lequel laquelle quand parce mais depuis jusqu entre aussi
quidem autem enim tamen igitur itaque propter inter super contra""".split())


def lang_guess(counts):
    """crude: which language's function words dominate"""
    probe = {"en": ("their", "which", "would", "there"), "de": ("werden", "haben", "nicht", "durch"),
             "es": ("cuando", "porque", "tambien", "entre"), "fr": ("lequel", "depuis", "aussi", "parce"),
             "la": ("quidem", "autem", "tamen", "igitur")}
    best, bn = "?", 0
    for lg, ws in probe.items():
        n = sum(counts.get(w, 0) for w in ws)
        if n > bn:
            best, bn = lg, n
    return best


def subject_terms(slug, files):
    """terms that appear in >= MIN_FILES of this subject's files, plus a language guess"""
    per_file, raw = defaultdict(int), Counter()
    n = 0
    for p in files:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")[:MAX_BYTES].lower()
        except Exception:
            continue
        n += 1
        seen = set()
        for w in WORD.findall(txt):
            raw[w] += 1
            if w not in seen:
                seen.add(w)
                per_file[w] += 1
    need = MIN_FILES if n >= MIN_FILES else 1
    keep = {w for w, c in per_file.items() if c >= need and w not in COMMON}
    if n == 1:
        keep = {w for w in keep if raw[w] >= 2}
    return keep, lang_guess(raw), n


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10 ** 6
    same_lang = "--same-language-only" in sys.argv

    # fingerprint files so an anthology sitting under two subjects is dropped from both
    seen_hash = defaultdict(set)
    subj_files = {}
    for d in sorted(FILES.iterdir()):
        if not d.is_dir():
            continue
        fs = sorted(d.glob("*.txt"))
        if not fs:
            continue
        subj_files[d.name] = fs
    for slug, fs in subj_files.items():
        for p in fs:
            try:
                h = hashlib.md5(p.read_bytes()[:200_000]).hexdigest()
            except Exception:
                continue
            seen_hash[h].add(slug)
    shared = {h for h, s in seen_hash.items() if len(s) > 1}

    terms, langs, nfiles = {}, {}, {}
    for i, (slug, fs) in enumerate(sorted(subj_files.items())):
        if i >= limit:
            break
        keep = []
        for p in fs:
            try:
                h = hashlib.md5(p.read_bytes()[:200_000]).hexdigest()
            except Exception:
                continue
            if h not in shared:
                keep.append(p)
        if not keep:
            continue
        t, lg, n = subject_terms(slug, keep)
        if len(t) < 50:
            continue
        terms[slug], langs[slug], nfiles[slug] = t, lg, n
        if (i + 1) % 25 == 0:
            print(f"  {i+1} subjects read", flush=True)

    print(f"{len(terms)} subjects with usable text; dropped {len(shared)} duplicated files")

    df = Counter()
    for t in terms.values():
        df.update(t)
    informative = {w for w, c in df.items() if 2 <= c <= DF_MAX}
    print(f"{len(df)} distinct terms; {len(informative)} informative (used by 2..{DF_MAX} subjects)")

    users = defaultdict(list)
    for slug, t in terms.items():
        for w in t & informative:
            users[w].append(slug)

    size = {s: len(t & informative) or 1 for s, t in terms.items()}
    pair_w, pair_terms = Counter(), defaultdict(list)
    for w, us in users.items():
        if len(us) < 2:
            continue
        weight = 1.0 / (len(us) - 1)
        for i in range(len(us)):
            for j in range(i + 1, len(us)):
                k = (us[i], us[j]) if us[i] < us[j] else (us[j], us[i])
                pair_w[k] += weight
                if len(pair_terms[k]) < 12:
                    pair_terms[k].append(w)

    scored = []
    for (a, b), s in pair_w.items():
        if same_lang and langs.get(a) != langs.get(b):
            continue
        scored.append((s / math.sqrt(size[a] * size[b]), s, a, b))
    scored.sort(reverse=True)

    known = set()
    cp = ATLAS / "connections.csv"
    if cp.exists():
        with open(cp, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                x, y = r.get("subject_slug"), r.get("counterpart_slug")
                if x and y:
                    known.add((x, y) if x < y else (y, x))

    top = scored[:TOP_PAIRS]
    hit = sum(1 for _, _, a, b in top if (a, b) in known)
    allp = len(scored)
    base = sum(1 for _, _, a, b in scored if (a, b) in known) / max(1, allp)
    print(f"\nvalidation: {hit}/{len(top)} of the top pairs are documented connections "
          f"({100*hit/max(1,len(top)):.0f}%), against a base rate of {100*base:.1f}% over all {allp} scored pairs")
    if base > 0:
        print(f"  lift over chance: {(hit/max(1,len(top)))/base:.1f}x")

    print("\ntop pairs by shared informative vocabulary:")
    print("%-26s %-26s %6s %4s  %s" % ("subject", "subject", "score", "lang", "terms"))
    for sc, raw, a, b in top[:28]:
        mark = "*" if (a, b) in known else " "
        print("%s%-25s %-26s %6.3f %2s/%-2s %s"
              % (mark, a[:25], b[:26], sc, langs.get(a, "?"), langs.get(b, "?"),
                 ", ".join(pair_terms[(a, b)][:6])))
    print("\n* = already a documented connection in connections.csv")

    OUT.write_text(json.dumps(
        {"pairs": [{"a": a, "b": b, "score": sc, "weight": raw, "known": (a, b) in known,
                    "terms": pair_terms[(a, b)]} for sc, raw, a, b in scored[:400]],
         "df_max": DF_MAX, "min_files": MIN_FILES, "subjects": len(terms)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
