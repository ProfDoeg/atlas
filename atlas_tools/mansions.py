#!/usr/bin/env python3
"""The 28 lunar mansions, manāzil al-qamar: the Picatrix's actual timing apparatus.

Anthony asked what the Picatrix says about tracking stars for practical magic. This is the answer,
and it was the gap in the Picatrix reading: the book's operations are timed by the Moon's passage
through 28 mansions, not by the twelve signs. The mansions are indigenous Arabic star lore, the
same body of names as the al-Jawzāʾ work: al-Thurayyā the Pleiades, al-Dabarān the follower,
al-Haqʿa the white spot on Orion's head.

TWO CONVENTIONS, and they are most of a mansion apart. Both are returned, labelled, never merged:

  "equal"      28 arcs of 12°51′26″ (360/28) measured from the vernal point. This is what a
               medieval practitioner read off a table, and what the Latin Picatrix inherits.
  "star"       the mansion is where its defining asterism actually is, precessing with the sky.

That is the same split as the tropical sign against the real constellation, arriving a third time
from a third direction. Choosing one silently would hide exactly what Anthony keeps asking to see.

    python3 atlas_tools/mansions.py 1888-05-01
    from atlas_tools.mansions import moon_mansion
    m = moon_mansion("1888-05-01")     # {"equal": {...}, "star": {...}}

CAVEAT, stated because it matters for anything built on this. The names, order and defining stars
below are the standard list and are secure. The star-keyed LONGITUDES are approximate: each is the
J2000 ecliptic longitude of the mansion's lead star, precessed to the date, and the boundaries are
taken midway between neighbours. Medieval sources do not agree on exact boundaries, and some
mansions are marked by a group rather than one star. Treat "star" as good to about a degree, not
as a critical edition. The "equal" convention has no such uncertainty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_ephemeris as CE

E = CE.E
ARC = 360.0 / 28.0          # 12°51′26″

# name, meaning, defining star(s), and that lead star's J2000 ecliptic longitude
MANSIONS = [
    ("al-Sharaṭān",            "the two signs",             "β, γ Arietis",                  29.0),
    ("al-Buṭayn",              "the little belly",          "ε, δ, ρ Arietis",               41.0),
    ("al-Thurayyā",            "the Pleiades",              "the Pleiades",                  59.9),
    ("al-Dabarān",             "the follower",              "Aldebaran, the Hyades",         69.8),
    ("al-Haqʿa",               "the white spot",            "λ, φ¹, φ² Orionis",             81.5),
    ("al-Hanʿa",               "the brand",                 "γ, ξ Geminorum",                91.0),
    ("al-Dhirāʿ",              "the forearm",               "Castor and Pollux",            109.0),
    ("al-Nathra",              "the gap",                   "Praesepe, γ δ Cancri",         127.5),
    ("al-Ṭarf",                "the glance",                "κ Cancri, λ Leonis",           140.0),
    ("al-Jabha",               "the forehead",              "Regulus, ζ γ η Leonis",        149.8),
    ("al-Zubra",               "the mane",                  "δ, θ Leonis",                  164.5),
    ("al-Ṣarfa",               "the turning",               "Denebola",                     171.4),
    ("al-ʿAwwāʾ",              "the barker",                "β η γ δ ε Virginis",           186.0),
    ("al-Simāk",               "the unarmed",               "Spica",                        203.8),
    ("al-Ghafr",               "the cover",                 "ι, κ, λ Virginis",             213.0),
    ("al-Zubānā",              "the claws",                 "α, β Librae",                  224.5),
    ("al-Iklīl",               "the crown",                 "β, δ, π Scorpii",              236.0),
    ("al-Qalb",                "the heart",                 "Antares",                      249.8),
    ("al-Shawla",              "the sting",                 "λ, υ Scorpii",                 264.5),
    ("al-Naʿāʾim",             "the ostriches",             "γ δ ε η, σ φ τ ζ Sagittarii",  275.0),
    ("al-Balda",               "the town, the empty place", "the gap in Sagittarius",       287.0),
    ("Saʿd al-Dhābiḥ",         "the slaughterer's luck",    "α, β Capricorni",              302.0),
    ("Saʿd Bulaʿ",             "the swallower's luck",      "ε, μ Aquarii",                 313.0),
    ("Saʿd al-Suʿūd",          "luckiest of the lucky",     "β Aquarii, ξ Capricorni",      322.0),
    ("Saʿd al-Akhbiya",        "the tents' luck",           "γ, π, ζ, η Aquarii",           334.0),
    ("al-Fargh al-Muqaddam",   "the fore spout",            "α, β Pegasi",                  353.0),
    ("al-Fargh al-Muʾakhkhar", "the hind spout",            "γ Pegasi, α Andromedae",         6.0),
    ("Baṭn al-Ḥūt",            "the belly of the fish",     "β Andromedae",                  17.0),
]
assert len(MANSIONS) == 28

# The Picatrix groups operations by mansion. These are the Gemini/Mercury ones Anthony asked for.
MERCURY_GEMINI = {"al-Hanʿa", "al-Dhirāʿ"}          # the two that fall across Gemini
PLEIADES_GROUP = {"al-Thurayyā", "al-Dabarān"}      # the al-Jawzāʾ neighbours, just before them


def _wrap(x):
    return x % 360.0


def equal_mansion(lon):
    """The table convention: 28 equal arcs from the vernal point."""
    i = int(_wrap(lon) / ARC) % 28
    n, meaning, stars, _ = MANSIONS[i]
    return {"index": i + 1, "name": n, "meaning": meaning, "stars": stars,
            "convention": "equal", "start_deg": round(i * ARC, 3), "width_deg": round(ARC, 3)}


def star_mansion(lon, jd):
    """The star convention: whichever mansion's defining asterism the Moon is nearest, with the
    boundary midway between neighbours. Longitudes precessed from J2000 to the date."""
    T = (jd - E.J2000) / 36525.0
    prec = E.precession_in_longitude(T) if hasattr(E, "precession_in_longitude") else 0.0
    pts = [(_wrap(l0 + prec), i) for i, (_, _, _, l0) in enumerate(MANSIONS)]
    best, bi = 1e9, 0
    for p, i in pts:
        d = abs(_wrap(lon - p + 180.0) - 180.0)
        if d < best:
            best, bi = d, i
    n, meaning, stars, l0 = MANSIONS[bi]
    return {"index": bi + 1, "name": n, "meaning": meaning, "stars": stars,
            "convention": "star", "lead_star_lon": round(_wrap(l0 + prec), 3),
            "moon_from_lead_deg": round(best, 2),
            "caveat": "boundaries midway between lead stars; good to about a degree"}


def moon_mansion(date_iso, hour_ut=0.0):
    y, m, d = (int(x) for x in date_iso.split("-")[:3])
    jd = E.julian_day(y, m, d, hour_ut / 24.0)
    lon = CE.longitudes(jd)["Moon"]
    return {"date": date_iso, "moon_lon": round(lon, 3),
            "equal": equal_mansion(lon), "star": star_mansion(lon, jd)}


def main(argv):
    if not argv:
        print(__doc__)
        print("  the 28, in order:")
        for i, (n, mg, st, l0) in enumerate(MANSIONS, 1):
            mark = "  <- Gemini/Mercury" if n in MERCURY_GEMINI else ("  <- al-Jawzāʾ neighbour" if n in PLEIADES_GROUP else "")
            print("   %2d  %-24s %-28s %s%s" % (i, n, mg, st, mark))
        return 0
    r = moon_mansion(argv[0])
    print("the Moon on %s, longitude %.3f°" % (r["date"], r["moon_lon"]))
    for k in ("equal", "star"):
        m = r[k]
        print("  %-6s %2d  %-24s %-26s %s" % (m["convention"], m["index"], m["name"], m["meaning"], m["stars"]))
    if r["equal"]["index"] != r["star"]["index"]:
        print("  the two conventions disagree, which is the point: %s by the table, %s by the stars."
              % (r["equal"]["name"], r["star"]["name"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
