#!/usr/bin/env python3
"""Creations read by their sky, the Picatrix way: Mercury and Gemini first.

Anthony, 2026-10-12: "I want a picatrix and astrology minded tooling that tracks creations of
objects or books or performances ... led by their meaning on that valence. Look for Mercury and
Gemini!!"

The Picatrix is a book of elections: a talisman works because it is made when the sky is right.
This tool turns that round and asks, of every creation the atlas already dates to the day, what
sky it was made under. A book printed, a work premiered, an object made, a house founded.

What it does, and what it does not:

  * Selects stops whose name or segment says something was made (keyword match, listed below,
    so a stop can be misclassified; every hit prints its stop name so a reader can see why).
  * Keeps only DAY-PRECISE dates. 01-01 is the atlas's year placeholder and dd=01 is very often a
    month placeholder; the Moon moves 13 degrees a day, so a placeholder day reads a false sky.
    Real events on the 1st of a month are lost by this rule. That is the price of not inventing.
  * Casts the sky with sky_on.py (the atlas ephemeris; Julian calendar before 1582-10-15),
    at 12:00 UT because creation times are almost never recorded. The Moon moves ~13 degrees a
    day, about one mansion, so the tool gives every mansion it crossed between 00:00 and 24:00 UT.
  * Scores Mercury with the classical dignity points as tabulated by William Lilly (1647):
    domicile +5, exaltation +4, detriment -5, fall -4, retrograde -5, combust -5, under the
    beams -4, cazimi +5. Lilly is later than the Picatrix; the points are a convention, not the
    Picatrix's own arithmetic. Wednesday, Mercury's day in the Picatrix's planetary week, adds +1.
  * Gemini is read twice, as everywhere in this atlas: the tropical sign, and the constellation
    the body actually stood in.
  * Lunar mansions come from nodus1's mansions.py, in BOTH its conventions, never merged: by the
    table (28 equal arcs from the vernal point, what the Latin Picatrix inherits) and by the stars
    (where the defining asterism actually is; good to about a degree). The meanings given are the
    names' meanings. The Picatrix's list of which operations suit which mansion is not in the
    atlas sources, so this tool does not invent one. The Gemini pair, al-Hanʿa and al-Dhirāʿ,
    get their own shortlist, labelled with the convention that put each creation there.

    python3 atlas_tools/picatrix_election.py            # writes readings/picatrix_mercury.md
    python3 atlas_tools/picatrix_election.py --top 40
"""
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATLAS = HERE.parent
sys.path.insert(0, str(HERE))
from sky_on import sky_on  # noqa: E402
import mansions as M  # noqa: E402

KINDS = [
    ("performance", r"premi[eè]re|first performance|first night|performed|staged|debut|concert|"
                    r"ballet|opera\b|the play\b|recital|sung\b"),
    ("book",        r"publish|\bprinted|\bprinting|\bedition|manuscript finished|written|writes|"
                    r"translat|manifesto|treatise|novel\b|pamphlet"),
    # bare "cast" left out: "the shadow cast", "cast out" outnumber castings
    ("object",      r"painted|painting|canvas|bronze|carved|sculpt|forged|minted|unveil|inscri|"
                    r"built|patent|the first .*(made|built)|talisman|engraved"),
    # "opens"/"opened" left out: a vault, a tomb or a case opened is not a creation
    ("founding",    r"founded|founding|foundation stone|consecrat|charter|inaugurat|launch"),
]
KIND_RE = [(k, re.compile(p, re.I)) for k, p in KINDS]
# nodus2's review: "the hull that was never launched" and "the city he founded" (a burial in it)
# match a keyword without being a creation. Both are excluded after the match.
NOT_CREATION = re.compile(
    r"never\s+(\w+\s+)?(launch|built|complet|finish|publish|found|written|printed)"
    r"|\b(he|she|they|who|which|that)\s+(\w+\s+){0,2}(founded|built|wrote|written|published)",
    re.I)

DOMICILE = {"Gemini", "Virgo"}
EXALT = {"Virgo"}
DETRIMENT = {"Sagittarius", "Pisces"}
FALL = {"Pisces"}
WEEKDAYS = ["Sunday (Sun)", "Monday (Moon)", "Tuesday (Mars)", "Wednesday (Mercury)",
            "Thursday (Jupiter)", "Friday (Venus)", "Saturday (Saturn)"]


# The one real creation NOT_CREATION throws out (7 of its 8 removals are right), restored by hand
# and marked as such in the report: Alfonsina Storni's writers' society, nodus1's catch.
RESTORED = {("1928-11-08", "Buenos Aires, the writers' society she built"): "founding"}


def kind_of(text):
    if NOT_CREATION.search(text):
        return None
    for k, rx in KIND_RE:
        if rx.search(text):
            return k
    return None


def day_precise(date):
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", date or "")
    return bool(m) and m.group(3) != "01"


def sep(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def read_sky(date):
    s = sky_on(date, hour_ut=12.0)
    b = s["bodies"]
    me, sun, moon = b["Mercury"], b["Sun"], b["Moon"]
    score, why = 0, []
    sg = me["sign"]
    if sg in DOMICILE:
        score += 5; why.append("in its own sign %s +5" % sg)
    if sg in EXALT:
        score += 4; why.append("exalted in Virgo +4")
    if sg in DETRIMENT:
        score -= 5; why.append("in detriment in %s -5" % sg)
    if sg in FALL:
        score -= 4; why.append("in fall in Pisces -4")
    if me["retrograde"]:
        score -= 5; why.append("retrograde -5")
    d = sep(me["lon"], sun["lon"])
    if d < 17 / 60:
        score += 5; why.append("cazimi, in the heart of the Sun +5")
    elif d < 8.5:
        score -= 5; why.append("combust, %.1f° from the Sun -5" % d)
    elif d < 17:
        score -= 4; why.append("under the beams, %.1f° from the Sun -4" % d)
    wd = int(math.floor(s["jd_ut"] + 1.5)) % 7
    if wd == 3:
        score += 1; why.append("a Wednesday +1")
    gem_trop = [n for n in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
                if b[n]["sign"] == "Gemini"]
    gem_con = [n for n in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn")
               if b[n]["constellation"] == "Gemini"]
    # the hour is unknown, so give every mansion the Moon crossed between 00:00 and 24:00 UT,
    # in both of mansions.py's conventions: the table (equal arcs) and the stars
    eq, st = [], []
    for h in (0.0, 6.0, 12.0, 18.0, 24.0):
        lon = sky_on(date, hour_ut=h)["bodies"]["Moon"]["lon"]
        jd = s["jd_ut"] + (h - 12.0) / 24.0
        for acc, m in ((eq, M.equal_mansion(lon)), (st, M.star_mansion(lon, jd))):
            if not acc or acc[-1]["index"] != m["index"]:
                acc.append(m)
    fmt = lambda ms: " → ".join("%d %s (%s)" % (m["index"], m["name"], m["meaning"]) for m in ms)
    names = {m["name"] for m in eq} | {m["name"] for m in st}
    return {
        "score": score, "why": why, "weekday": WEEKDAYS[wd],
        "mercury": me["sign_text"], "mercury_con": me["constellation"],
        "sun": sun["sign_text"], "moon": moon["sign_text"],
        "gem_trop": gem_trop, "gem_con": gem_con,
        "mansion": "by the table %s · by the stars %s" % (fmt(eq), fmt(st)),
        "gemini_mansion": sorted(names & M.MERCURY_GEMINI),
        "gemini_mansion_by": ", ".join(
            c for c, ms in (("table", eq), ("stars", st))
            if any(m["name"] in M.MERCURY_GEMINI for m in ms)),
    }


def journey_rows_not_in_catalog(have):
    """Stops from journeys built after catalog_stops.csv was last regenerated. Read straight from
    the journey files rather than regenerating the catalog here, which is the pipeline's job."""
    rows = []
    for path in sorted(ATLAS.glob("*.journey.json")):
        slug = path.name[:-len(".journey.json")]
        if slug in have:
            continue
        j = json.load(open(path, encoding="utf-8"))
        for seg in j.get("segments", []):
            for st in seg.get("stops", []):
                rows.append({"slug": slug, "traveler": j.get("traveler", slug),
                             "segment": seg.get("name", ""), "stop_name": st.get("name", ""),
                             "date": st.get("date", "")})
    return rows


def collect():
    rows = list(csv.DictReader(open(ATLAS / "catalog_stops.csv", encoding="utf-8")))
    rows += journey_rows_not_in_catalog({r["slug"] for r in rows})
    out = []
    for r in rows:
        if not day_precise(r["date"]):
            continue
        # stop name only: segment titles ("The Book Outlives the State") would tag every stop in them
        k = kind_of(r["stop_name"])
        restored = (r["date"], r["stop_name"]) in RESTORED
        if restored:
            k = RESTORED[(r["date"], r["stop_name"])]
        if not k:
            continue
        out.append(dict(r, kind=k + (" (restored by hand)" if restored else ""),
                        sky=read_sky(r["date"])))
    return out


def line(c):
    s = c["sky"]
    g = []
    if s["gem_trop"]:
        g.append("Gemini (sign): " + ", ".join(s["gem_trop"]))
    if s["gem_con"]:
        g.append("Gemini (stars): " + ", ".join(s["gem_con"]))
    return ("- **%s** · %s · %s — *%s* (%s)\n  Mercury %s, among the stars of %s · score **%+d**: %s\n"
            "  Sun %s · Moon %s, mansion %s · %s%s\n" % (
                c["date"], c["kind"], c["traveler"], c["stop_name"], c["slug"],
                s["mercury"], s["mercury_con"], s["score"], "; ".join(s["why"]) or "no dignity either way",
                s["sun"], s["moon"], s["mansion"], s["weekday"],
                (" · " + " · ".join(g)) if g else ""))


def report(cs, top):
    kinds = Counter(c["kind"] for c in cs)
    best = sorted(cs, key=lambda c: (-c["sky"]["score"], c["date"]))
    gem = [c for c in cs if "Mercury" in c["sky"]["gem_trop"] or "Sun" in c["sky"]["gem_trop"]
           or "Moon" in c["sky"]["gem_trop"]]
    gem_star = [c for c in cs if "Mercury" in c["sky"]["gem_con"]]
    worst = sorted(cs, key=lambda c: (c["sky"]["score"], c["date"]))
    n_me_dom = sum(1 for c in cs if c["sky"]["mercury"].split()[0] in DOMICILE)
    wed = sum(1 for c in cs if c["sky"]["weekday"].startswith("Wednesday"))
    o = ["# Creations under Mercury: a Picatrix reading of the atlas\n",
         "Generated by `atlas_tools/picatrix_election.py`. Read its docstring for the method and its "
         "limits: creation stops are found by keyword, only day-precise dates are used, the sky is "
         "cast at 12:00 UT, and Mercury is scored with Lilly's dignity points plus +1 for Wednesday.\n",
         "**Creations read:** %d (%s).\n" % (len(cs), ", ".join("%s %d" % kv for kv in kinds.most_common())),
         "**Mercury in its own signs (Gemini/Virgo):** %d of %d, %.0f%%. By chance alone, Mercury "
         "spends roughly a sixth of the time in those two signs, so about 17%% would be expected.\n"
         % (n_me_dom, len(cs), 100.0 * n_me_dom / max(1, len(cs))),
         "**Made on a Wednesday:** %d of %d, %.0f%% (chance: 14%%).\n"
         % (wed, len(cs), 100.0 * wed / max(1, len(cs))),
         "\n## The strongest Mercury: top %d\n" % top]
    o += [line(c) for c in best[:top]]
    o.append("\n## Gemini creations: Sun, Moon or Mercury in tropical Gemini (%d)\n" % len(gem))
    o += [line(c) for c in sorted(gem, key=lambda c: c["date"])]
    o.append("\n## Mercury among the stars of Gemini, the constellation reading (%d)\n" % len(gem_star))
    o += [line(c) for c in sorted(gem_star, key=lambda c: c["date"])]
    gm = [c for c in cs if c["sky"]["gemini_mansion"]]
    o.append("\n## The Moon in a Gemini mansion, al-Hanʿa or al-Dhirāʿ (%d)\n" % len(gm))
    o.append("Each line says which convention put the Moon there: the table, the stars, or both.\n")
    o += [line(c).rstrip("\n") + "\n  Gemini mansion by: **%s**\n" % c["sky"]["gemini_mansion_by"]
          for c in sorted(gm, key=lambda c: c["date"])]
    o.append("\n## The weakest Mercury: made against the sky, bottom %d\n" % min(top, 20))
    o += [line(c) for c in worst[:min(top, 20)]]
    return "".join(o)


def main():
    top = 30
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    cs = collect()
    out = ATLAS / "readings" / "picatrix_mercury.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report(cs, top), encoding="utf-8")
    print("%d creations read; report at %s" % (len(cs), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
