#!/bin/bash
# Keeps fetching until the catalogue stops growing.
#
# corpus_fetch.py works through the availability records that exist WHEN IT STARTS. The catalogue
# (corpus_availability.py) is still writing new ones, so a single fetch pass always leaves the late arrivals
# behind. This waits for the current pass to finish, then re-runs until a pass adds no new files, which is also
# how failed items get their retry: both tools skip what they already have, so a re-run costs nothing for work
# already done and picks up only what is missing.
#
# Deliberately a loop and not an agent: every decision here is already made in code -- which editions are free
# (corpus_availability's gate), which format to take, what to skip -- so there is nothing for a model to judge
# and a model would only be a slower way to type the same command. The land_subject.py precedent.
#
#   tmux new-session -d -s fetchsup "bash ~/corpus/fetch_supervisor.sh"
set -u
T=/home/drdoeg/taller/atlas/atlas_tools
L=/home/drdoeg/corpus
LOG=$L/supervisor.log
echo "=== supervisor up $(date -Is)" >> "$LOG"

# never run two fetchers at once
while tmux has-session -t =fetch 2>/dev/null; do sleep 60; done

prev=0
for pass in 1 2 3 4 5 6 7 8; do
    echo "=== pass $pass $(date -Is)" >> "$LOG"
    python3 "$T/corpus_fetch.py" --budget-gb 50 >> "$LOG" 2>&1
    now=$(find "$L/files" -type f ! -name 'manifest.json' 2>/dev/null | wc -l)
    echo "--- pass $pass done, $now files on disk (was $prev) $(date -Is)" >> "$LOG"
    # stop only when a pass added nothing AND the catalogue itself has finished
    if [ "$now" -eq "$prev" ] && ! tmux has-session -t =corpus 2>/dev/null; then
        echo "=== steady: no new files and the catalogue is finished $(date -Is)" >> "$LOG"
        break
    fi
    prev=$now
    sleep 300
done
echo "=== supervisor done $(date -Is)" >> "$LOG"
