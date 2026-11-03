#!/bin/sh
# Join libtorch_cpu.so from its layer chunks on first start, then run the server.
set -e
LIB=/usr/local/lib/python3.11/site-packages/torch/lib/libtorch_cpu.so
if [ ! -f "$LIB" ]; then
    cat /parts/libtorch_cpu.so.part0 /parts/libtorch_cpu.so.part1 \
        /parts/libtorch_cpu.so.part2 /parts/libtorch_cpu.so.part3 > "$LIB"
    rm -rf /parts
fi
exec python server.py
