#!/usr/bin/env bash
# Build a copy of HotSpot that prints temperatures with 6 decimals instead of 2, and whose grid
# transient solver reuses its LU factorisation (docs/plan.md P0-4).
# The stock build at ~/projects/HotSpot stays untouched.
#   usage (inside WSL):  bash setup/build_hotspot_ltp.sh
# Result: ~/projects/HotSpot-ltp/hotspot, and setup/ltp.patch (the diff that was applied).
set -euo pipefail

SRC=${HOTSPOT_SRC:-$HOME/projects/HotSpot}
DST=${HOTSPOT_LTP:-$HOME/projects/HotSpot-ltp}
HERE=$(cd "$(dirname "$0")" && pwd)

rm -rf "$DST" && mkdir -p "$DST/orig"
cp "$SRC"/*.c "$SRC"/*.h "$SRC"/Makefile "$SRC"/*.config "$SRC"/LICENSE "$DST"/
cd "$DST"
sed -i 's/\r$//' *.c *.h Makefile    # the HotSpot sources have CRLF endings; keep diffs clean
cp hotspot.c temperature_block.c temperature_grid.c orig/

# %.2f -> %.6f only in the functions that write temperatures:
#   hotspot.c write_vals (.ttrace), temperature_block.c dump_temp_block (.steady, block model),
#   temperature_grid.c grid dumps and dump_temp_grid (.steady / grid maps, grid model).
sed -i '/^void write_vals/,/^}/s/%\.2f/%.6f/g' hotspot.c
sed -i '/^void dump_temp_block(/,/^}/s/%\.2f/%.6f/g' temperature_block.c
sed -i -e '/^void dump_steady_temp_grid/,/^}/s/%\.2f/%.6f/g' \
       -e '/^void dump_transient_temp_grid/,/^}/s/%\.2f/%.6f/g' \
       -e '/^void dump_temp_grid(/,/^}/s/%\.2f/%.6f/g' temperature_grid.c

#   temperature.c: optional stronger leakage for P4-3 (LTP_LEAK_ALPHA=1.5e+5 -> 10x the default)
if [ -n "${LTP_LEAK_ALPHA:-}" ]; then
  sed -i "s/double leak_alpha = 1.5e+4;/double leak_alpha = ${LTP_LEAK_ALPHA};/" temperature.c
fi

#   temperature_grid.c: fix a memory leak in the grid transient (SuperLU build). Every step
#   allocates the node power vector (~130 kB at 64x64) and never frees it, so a 60,000-step
#   trace needs ~8 GB and is killed. Free it after the solve.
sed -i 's/^  backward_euler(G, C, T, P, &h, T);$/&\n  SUPERLU_FREE(P);  \/* LTP: fix leak *\//' temperature_grid.c
grep -q "LTP: fix leak" temperature_grid.c || { echo "leak fix not applied"; exit 1; }

#   temperature_grid.c: optional matrix dump for P3-4 (LTP_DUMP_BUILD=1, separate build only)
if [ -n "${LTP_DUMP_BUILD:-}" ]; then
  python3 "$HERE/patch_dump.py" temperature_grid.c
fi

#   hotspot.c: flush the .ttrace after every row, so HotSpot can be driven step by step through
#   pipes (closed-loop DTM, P6-1: power rows in on a pipe, temperature rows out on a FIFO).
sed -i -e 's/^\(\s*\)write_vals(tout, vals, n);/&\n\1fflush(tout);/' \
       -e 's/^\(\s*\)write_names(tout, names, n);/&\n\1fflush(tout);/' hotspot.c

#   RCutil.c backward_euler: factorise once per step size instead of every step (speed only).
#   (LTP_NO_BE_CACHE=1 skips this; used once to build ~/projects/HotSpot-prec for comparison.)
cp RCutil.c orig/
if [ -z "${LTP_NO_BE_CACHE:-}" ]; then
  python3 "$HERE/patch_be_cache.py" RCutil.c
fi

: > ltp.patch
for f in hotspot.c temperature_block.c temperature_grid.c RCutil.c; do
  diff -u --label "a/$f" --label "b/$f" "orig/$f" "$f" >> ltp.patch || true
done
rm -rf orig
if [ -z "${LTP_NO_BE_CACHE:-}${LTP_LEAK_ALPHA:-}${LTP_DUMP_BUILD:-}" ]; then cp ltp.patch "$HERE/ltp.patch"; fi
echo "changed lines: $(grep -c '^+[^+]' ltp.patch)"

make SUPERLU=1 -j8 > build.log 2>&1 || { tail -20 build.log; exit 1; }
ls -la "$DST/hotspot"
