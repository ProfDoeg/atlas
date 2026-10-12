#!/usr/bin/env python3
"""Group astrology: distributions and chart interactions for a set of subjects.

Anthony, 2026-10-12: the 1888 cohort gathers in particular cities, and he wants their charts, the
interactions inside each group, triads, distributions, and whether the whole 888 clusters at all.

Two honesty rules, because this is the kind of question where it is easy to fool yourself:

  1. BOTH READINGS. Every body is counted twice, by tropical sign and by the constellation it
     actually stood in. They differ by most of a sign for 19th-century births.
  2. SAY WHEN IT IS NOISE. A group of twelve people has about one Sun per sign; two in a sign is
     ordinary. Every distribution is reported against the 888-chart baseline with the count you
     would expect by chance, and a flag only when it is well outside it. No flag, no finding.

Usage:
    python3 atlas_tools/group_sky.py --baseline
    python3 atlas_tools/group_sky.py --group "Barcelona" --members slugs.txt
    python3 atlas_tools/group_sky.py --cities 1888_cross_reference.txt
"""
import json, math, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATLAS = HERE.parent
CHARTS = ATLAS / "zodiac" / "charts"
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricornus", "Aquarius", "Pisces"]
ELEMENT = {"Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
           "Taurus": "earth", "Virgo": "earth", "Capricornus": "earth",
           "Gemini": "air", "Libra": "air", "Aquarius": "air",
           "Cancer": "water", "Scorpio": "water", "Pisces": "water"}
MODE = {"Aries": "cardinal", "Cancer": "cardinal", "Libra": "cardinal", "Capricornus": "cardinal",
        "Taurus": "fixed", "Leo": "fixed", "Scorpio": "fixed", "Aquarius": "fixed",
        "Gemini": "mutable", "Virgo": "mutable", "Sagittarius": "mutable", "Pisces": "mutable"}
ASPECTS = [("conjunction", 0, 8), ("sextile", 60, 4), ("square", 90, 7),
           ("trine", 120, 7), ("opposition", 180, 8)]
SLOW = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")


def load_charts():
    out = {}
    for p in sorted(CHARTS.glob("*.chart.json")):
        try:
            c = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if "bodies" in c:
            out[c.get("slug", p.stem.replace(".chart", ""))] = c
    return out


def name_of(c):
    return c.get("traveler") or c.get("title") or c.get("slug")


def sign_counts(charts, body, key="sign"):
    return Counter(c["bodies"][body][key] for c in charts if body in c.get("bodies", {})
                   and c["bodies"][body].get(key))


def expected_flags(obs, n, baseline, label):
    """Report counts against the baseline share, flagging only what is well outside chance.
    Binomial: sd = sqrt(n p (1-p)). Flag at 2.5 sd AND at least 3 over expected, which for these
    group sizes is the point where it stops being the sort of lump any random dozen people show."""
    lines, flags = [], []
    total_base = sum(baseline.values()) or 1
    for s, k in obs.most_common():
        p = baseline.get(s, 0) / total_base
        exp = n * p
        sd = math.sqrt(n * p * (1 - p)) if 0 < p < 1 else 0.0
        z = (k - exp) / sd if sd > 0 else 0.0
        mark = ""
        if k - exp >= 3 and z >= 2.5:
            mark = "  <-- well outside chance"
            flags.append((s, k, exp, z))
        lines.append("    %-14s %2d   expected %4.1f   %+.1f sd%s" % (s, k, exp, z, mark))
    return lines, flags


def aspects_between(a, b, bodies=None):
    """Cross-chart aspects between two people. Slow-planet pairs are dropped: people born within
    a few years of each other share them by generation, so they say nothing about the pair."""
    out = []
    ba, bb = a.get("bodies", {}), b.get("bodies", {})
    names = bodies or [n for n in ba if n in bb and not n.endswith("Node")]
    for x in names:
        for y in names:
            if x not in ba or y not in bb:
                continue
            if x in SLOW and y in SLOW:
                continue
            d = abs(ba[x]["longitude"] - bb[y]["longitude"]) % 360.0
            d = min(d, 360.0 - d)
            for nm, ang, orb in ASPECTS:
                if abs(d - ang) <= orb:
                    out.append((x, nm, y, round(abs(d - ang), 2)))
    return out


def main(argv):
    charts = load_charts()
    if "--baseline" in argv:
        print("BASELINE over %d charts" % len(charts))
        cs = list(charts.values())
        for key, lab in (("sign", "tropical sign"), ("constellation", "constellation")):
            cnt = sign_counts(cs, "Sun", key)
            if not cnt:
                print("\n  Sun by %s: not recorded in these charts yet" % lab)
                continue
            print("\n  Sun by %s:" % lab)
            for s, k in cnt.most_common():
                print("    %-14s %3d  %5.1f%%" % (s, k, 100.0 * k / sum(cnt.values())))
        return 0
    if "--cities" in argv:
        xref = argv[argv.index("--cities") + 1]
        cities = [c.strip() for c in (argv[argv.index("--in") + 1].split(",")
                  if "--in" in argv else ["Barcelona", "Vienna", "London", "Paris", "Buenos Aires"])]
        by_name = {}
        for slug, c in charts.items():
            by_name[name_of(c).lower()] = slug
        groups = defaultdict(set)
        unmatched = set()
        for line in open(xref, encoding="utf-8"):
            if "\t" not in line:
                continue
            nm, _, place = (line.rstrip("\n").split("\t") + ["", ""])[:3]
            for city in cities:
                if city.lower() in place.lower():
                    key = nm.lower()
                    slug = by_name.get(key)
                    if slug is None:                       # try the name before any parenthesis
                        bare = re.sub(r"\s*\(.*", "", nm).strip().lower()
                        slug = by_name.get(bare)
                        if slug is None:
                            for k, v in by_name.items():
                                if k.startswith(bare[:18]) or bare.startswith(k[:18]):
                                    slug = v
                                    break
                    if slug:
                        groups[city].add(slug)
                    else:
                        unmatched.add(nm)
        base_sign = sign_counts(list(charts.values()), "Sun", "sign")
        base_con = sign_counts(list(charts.values()), "Sun", "constellation")
        print("1888 BY CITY, against the %d-chart baseline" % len(charts))
        if unmatched:
            print("  (no chart for %d of the named: %s)" % (len(unmatched), "; ".join(sorted(unmatched)[:4])))
        for city in cities:
            mem = sorted(groups.get(city, []))
            if not mem:
                print("\n%s: nobody with a chart" % city)
                continue
            cs = [charts[s] for s in mem]
            print("\n%s: %d with charts" % (city.upper(), len(cs)))
            print("  " + ", ".join(name_of(c) for c in cs))
            for key, lab, base in (("sign", "Sun by sign", base_sign),
                                   ("constellation", "Sun by constellation", base_con)):
                obs = sign_counts(cs, "Sun", key)
                lines, flags = expected_flags(obs, len(cs), base, lab)
                print("  %s:" % lab)
                for l in lines[:5]:
                    print(l)
                if not flags:
                    print("    nothing outside chance")
            # the interactions inside the group
            pairs = []
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    a = aspects_between(cs[i], cs[j])
                    tight = [x for x in a if x[3] <= 2.0]
                    if tight:
                        pairs.append((len(tight), name_of(cs[i]), name_of(cs[j]), tight[:3]))
            pairs.sort(reverse=True)
            if pairs:
                print("  tightest chart interactions in the group (orb under 2°):")
                for n, a, b, ex in pairs[:4]:
                    print("    %s / %s: %d" % (a, b, n))
                    for x, nm, y, orb in ex:
                        print("       %s %s %s (%.1f°)" % (x, nm, y, orb))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
