#!/usr/bin/env python3
"""How often do Sun, Mercury and Moon all stand in Gemini at once?

nodus3's picatrix_election found 2 such days among 423 day-precise creations in the atlas (Saint
Mercurius 363, and Garay's founding of Buenos Aires in 1580). The question that decides whether
that means anything is: how many would you expect by chance? You cannot just multiply the three
probabilities, because Mercury never strays more than about 28° from the Sun, so the two are
strongly dependent. So measure it instead: sample dates across the atlas's own span and count.
"""
import random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_ephemeris as CE

E = CE.E
GEMINI = 2                      # sign index, 0 = Aries


def all_three_in(sign_index, jd):
    lons = CE.longitudes(jd)
    return all(E.sign_of(lons[b])[0] == sign_index for b in ("Sun", "Mercury", "Moon"))


def main(argv):
    n = int(argv[0]) if argv else 20000
    observed_in, observed_n = 2, 423           # nodus3's counts, for the comparison
    jd0 = E.julian_day(300, 1, 1, 0.0)         # the atlas runs from late antiquity to now
    jd1 = E.julian_day(2026, 1, 1, 0.0)
    rnd = random.Random(7)
    hits = 0
    for _ in range(n):
        jd = rnd.uniform(jd0, jd1)
        if all_three_in(GEMINI, jd):
            hits += 1
    rate = hits / n
    exp = rate * observed_n
    print("Sun, Mercury and Moon all in Gemini")
    print("  sampled %d random days between 300 and 2026: %d hits, rate %.5f" % (n, hits, rate))
    print("  so in %d day-precise creations you expect %.2f by chance" % (observed_n, exp))
    print("  nodus3 found %d" % observed_in)
    if exp > 0:
        import math
        # Poisson: how surprising is the observed count at this rate?
        p_ge = 1.0 - sum(math.exp(-exp) * exp ** k / math.factorial(k) for k in range(observed_in))
        print("  P(%d or more by chance) = %.2f" % (observed_in, p_ge))
        print("  verdict: %s" % ("ordinary; this is what chance looks like" if p_ge > 0.1 else
                                 "worth a second look"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
