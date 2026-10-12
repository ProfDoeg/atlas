#!/usr/bin/env python3
"""The sky over a given day: the companion to a year slice.

Anthony, 2026-10-12: "I want to do 1888". nodus2 builds the roster and the convergences — who was
alive, which stops are dated into the year, where subjects meet in the same place at the same time.
This is the other half: what the sky was doing over any one of those days, so a dated stop can carry
its own sky rather than a generic one for the year.

Call it from a year tool:

    from atlas_tools.sky_on import sky_on
    s = sky_on("1888-05-01")                       # geocentric, no place
    s = sky_on("1888-05-01", lat=51.5, lng=-0.13)  # with the angles, if the stop has coordinates

or from a shell:

    python3 atlas_tools/sky_on.py 1888-05-01
    python3 atlas_tools/sky_on.py 1888-05-01 51.5 -0.13

Two readings are returned for every body, and the difference matters for this atlas: `sign` is the
tropical sign, `constellation` is where the body actually stood against the stars. In 1888 they are
most of a sign apart, and the constellation is the Dantean reading Anthony has been working in.

Uses atlas_tools/chart_ephemeris.py — the repo's own, the same one behind the 888 natal charts —
so a year tool needs nothing from outside the atlas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_ephemeris as CE

# chart_ephemeris loads the base ephemeris by PATH (ATLAS_EPHEMERIS, defaulting into
# ~/private_notes/essay_gemini/reels/ephemeris.py), so it is not importable by name. Reuse the
# module it already loaded rather than loading a second copy.
# NOTE: that means the atlas repo depends on a file outside it. It works here and on nodus3
# because private_notes was copied there, but a clone without private_notes will fail at import
# with "ephemeris not found" — set ATLAS_EPHEMERIS, or move the ephemeris into the repo.
E = CE.E

BODIES = CE.BODIES


def julian_day(date_iso, hour_ut=0.0):
    """ISO date -> JD(UT). Julian calendar before 1582-10-15, as everywhere else in the atlas."""
    y, m, d = (int(x) for x in date_iso.split("-")[:3])
    return E.julian_day(y, m, d, hour_ut / 24.0)


def sky_on(date_iso, hour_ut=0.0, lat=None, lng=None):
    """The sky over one day. lat/lng (degrees, east positive) add the ascendant and midheaven."""
    jd = julian_day(date_iso, hour_ut)
    lons = CE.longitudes(jd)
    spd = CE.speeds(jd)
    out = {"date": date_iso, "jd_ut": jd, "bodies": {}}
    # longitudes() and speeds() are dicts keyed by body NAME (speeds covers only the movers)
    for name in BODIES:
        if name not in lons:
            continue
        lon = lons[name]
        si, deg = E.sign_of(lon)
        out["bodies"][name] = {
            "lon": lon,
            "sign": CE.SIGNS[si],
            "sign_text": "%s %d°%02d′" % (CE.SIGNS[si], int(deg), int(round((deg % 1) * 60))),
            "constellation": E.constellation_of(lon),
            "retrograde": bool(spd[name] < 0) if name in spd else None,
        }
    if lat is not None and lng is not None:
        a = CE.angles(jd, lat, lng)
        # angles() also returns ramc, lst and eps — working values, not points on the zodiac.
        # Rendering obliquity as a sign is meaningless, so only the four real angles come out.
        out["angles"] = {k: {"lon": a[k], "sign": CE.SIGNS[E.sign_of(a[k])[0]],
                             "text": "%s %d°%02d′" % (CE.SIGNS[E.sign_of(a[k])[0]],
                                                      int(E.sign_of(a[k])[1]),
                                                      int(round((E.sign_of(a[k])[1] % 1) * 60)))}
                         for k in ("asc", "mc", "desc", "ic") if k in a}
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    date_iso = sys.argv[1]
    lat = float(sys.argv[2]) if len(sys.argv) > 3 else None
    lng = float(sys.argv[3]) if len(sys.argv) > 3 else None
    s = sky_on(date_iso, lat=lat, lng=lng)
    print("the sky over %s" % s["date"])
    print("  %-10s %-22s %-16s %s" % ("body", "sign", "constellation", ""))
    for name, b in s["bodies"].items():
        print("  %-10s %-22s %-16s %s" % (name, b["sign_text"], b["constellation"],
                                          "retrograde" if b["retrograde"] else ""))
    if "angles" in s:
        print("  --- angles at the place given ---")
        for k, v in s["angles"].items():
            print("  %-10s %s" % (k, v["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
