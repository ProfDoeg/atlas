#!/usr/bin/env python3
"""Ask the Codex machine what a person MADE, for the atlas subjects whose dossier never asked.

Why this exists. 14 atlas subjects have a Codex dossier with no "Works by" section at all -- Michelangelo,
Francis Bacon, Aby Warburg, Carlos Gardel among them -- so their bibliographies come out empty. They were
researched as biographies and the question was never put. The obvious fix, a Claude subagent with web search,
is closed: this session spent its 200 searches and a subagent SHARES the parent's budget rather than getting a
fresh one (tested 2026-10-14, the agent returned BUDGET_EXHAUSTED after two calls). The Codex CLI has its own
token pool and its own web search, so it can answer when we cannot.

What it asks for, and why not simply "list their works". Anthony, 2026-10-14: "the more you try to lock into a
strict pipeline and definition then you will miss the jewels. Every text is different. You will be asking
repeatedly: What is this text? What is a text? Is this a text?" -- and then the vocabulary he wants used:
"Gesamtkunstwerk, project, creation, obra... manifesto, manifestation, protocol". Those are not synonyms. Obra
is the made thing whatever its medium. A project may be unfinished and still be the work, which is exactly
Warburg's Bilderatlas, panels on screens and he dead in 1929. A manifesto is a text that acts; a protocol is a
text that instructs. Manifestation says the thing appeared rather than that anyone made it, which half this
atlas would claim of its own work. So the prompt asks what the person MADE and lets the answer name its own
kind, instead of forcing a tango, a ceiling and an unfinished atlas into one schema built for printed books.

Output goes to ~/codex_lab/out_works/<slug>.works.md and is NOT auto-staged: these are read by a human first,
then copied into the atlas's dossiers/ where corpus_inventory.py picks them up alongside the dossier.

    python3 codex_works_runner.py aby_warburg carlos_gardel
    python3 codex_works_runner.py --file /home/drdoeg/codex_lab/works_worklist.txt
"""
import csv
import os
import re
import subprocess
import sys
import time

HOME = '/home/drdoeg'                    # pinned: the codexbatch tmux server carries another HOME and the
                                          # Codex auth lives under this one
LAB = f'{HOME}/codex_lab'
REPO = f'{HOME}/taller/atlas'
OUT = f'{LAB}/out_works'
CODEX = f'{HOME}/.local/bin/codex'
LOG = f'{LAB}/works.log'
TIMEOUT = 3600


def log(msg):
    line = time.strftime('%m-%d %H:%M:%S ') + msg
    print(line, flush=True)
    open(LOG, 'a').write(line + '\n')


def traveler(slug):
    with open(f'{REPO}/catalog_subjects.csv', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            if r['slug'] == slug:
                return r['traveler'].split('(')[0].split(',')[0].strip(), r.get('years', '')
    return None, ''


PROMPT = """You are compiling, for an atlas of historical journeys, a cited list of everything {name} MADE.{yrs}

Do not ask "what books did this person write". Ask what they made, and what kind of thing each one is.

The atlas's owner put it this way: "Every text is different. You will be asking repeatedly: What is this text?
What is a text? Is this a text?" He offered this vocabulary, and the words are not synonyms:

  obra -- the made thing itself, whatever the medium: a book, a building, a body of work
  project -- the intention; a project may be unfinished and still be the work
  creation, manifestation -- a thing that appeared, which is not quite the same as a thing someone made
  manifesto -- a text that acts rather than describes
  protocol -- a text that instructs
  Gesamtkunstwerk -- a thing that refuses the separation of media

Use whichever of these actually fit this person, and invent your own category when none of them do. A tango is
not a book. A ceiling is not a book. An unfinished atlas of photographic panels is not a book. Where a thing
resists being called a work at all, SAY SO in its entry: that resistance is information, not a failure to
classify.

RULES.
1. Build the list from the standard scholarly bibliography, catalogue raisonne, collected-works edition or
   discography for this person. Do NOT build it from a library catalogue search. Library results are EDITIONS,
   translations, reprints and books written ABOUT the person, which is a different thing from what they made.
2. Cite what you used. Every claim that something exists must be traceable.
3. Where authorship, dating, attribution or completeness is disputed, state the dispute rather than silently
   resolving it.
4. Never invent a date or a title to fill the shape. If a thing has no fixed title or date, describe it instead.
5. NAME works; do not REPRODUCE them. Never quote song lyrics, poems, or any substantial passage of a text that
   may still be in copyright. This list goes into a repository that is mirrored publicly, so quoting the words
   of a tango or a poem would publish copyrighted text; naming it, dating it and describing it does not.
   (Added 2026-10-16 after nodus2 checked the music subjects for exactly this: Discepolo died in 1951 and
   Alfredo Le Pera in 1935, so their lyrics remain in copyright. The check came back clean, and the rule is
   written down here so the next batch cannot wander into it.)

FORMAT. Markdown, and nothing else before or after it. Begin with exactly this line:

## Works by {name}

Then "### " subheadings in categories that fit THIS person in their own terms. Under each, one bullet per thing:

- **<date or range>:** *<Title>*. <One or two sentences: what kind of object it is, its status, and anything
  that makes it resist an easy category.>

Keep the bold date and italic title where they genuinely apply, because a parser reads them, but never force
them. End with a "### Sources" section listing the actual sources you consulted, with URLs where they exist.

Print the whole document to stdout. Do not write any file."""


def run_one(slug):
    name, years = traveler(slug)
    if not name:
        log(f'{slug}: NOT IN CATALOG, skipped')
        return False
    yrs = f' ({years})' if years else ''
    prompt = PROMPT.format(name=name, yrs=yrs)
    logfile = f'{LAB}/works_{slug}.log'
    log(f'{slug}: run ({name})')
    try:
        with open(logfile, 'w') as lf:
            subprocess.run([CODEX, 'exec', '-s', 'workspace-write', '--skip-git-repo-check',
                            '-C', LAB, '-c', 'tools.web_search=true', '-'],
                           input=prompt, stdout=lf, stderr=subprocess.STDOUT,
                           text=True, timeout=TIMEOUT,
                           env={**os.environ, 'HOME': HOME,
                                'PATH': f'{HOME}/.local/bin:' + os.environ.get('PATH', '')})
    except subprocess.TimeoutExpired:
        log(f'{slug}: TIMEOUT after {TIMEOUT // 60} min')
        return False
    text = open(logfile, encoding='utf-8', errors='replace').read()
    marker = '## Works by'
    i = text.rfind(marker)
    if i < 0:
        log(f'{slug}: no works list in output, tail: ' + text[-160:].replace('\n', ' '))
        return False
    doc = re.sub(r'\ntokens used\n[\d,]+\s*$', '\n', text[i:])
    # the dossier runner's hard-won rule: a real document never contains a literal CLI "ERROR: " line, and
    # checking for that catches every flavour of network/quota failure without enumerating their wordings
    if re.search(r'\nERROR: ', doc):
        log(f'{slug}: output contains an ERROR: line, discarding')
        return False
    if 'http' not in doc:
        log(f'{slug}: no citable source in output, holding anyway for a human read')
    os.makedirs(OUT, exist_ok=True)
    open(f'{OUT}/{slug}.works.md', 'w', encoding='utf-8').write(doc)
    n = doc.count('\n')
    log(f'{slug}: DONE {n} lines -> {OUT}/{slug}.works.md')
    return True


def main():
    args = sys.argv[1:]
    if '--file' in args:
        path = args[args.index('--file') + 1]
        slugs = [l.strip() for l in open(path) if l.strip() and not l.startswith('#')]
    else:
        slugs = [a for a in args if not a.startswith('-')]
    if not slugs:
        raise SystemExit(__doc__)
    log(f'=== works runner, {len(slugs)} subjects')
    ok = 0
    for s in slugs:
        if os.path.exists(f'{OUT}/{s}.works.md'):
            log(f'{s}: already done, skipping')
            continue
        if run_one(s):
            ok += 1
    log(f'=== finished: {ok} of {len(slugs)} written to {OUT}')


if __name__ == '__main__':
    main()
