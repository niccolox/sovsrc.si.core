FROM python:3.11-slim AS deps

# Install the CPU-only torch wheel first. A per-line index URL in a
# requirements file does not work, and the default PyPI wheel pulls in
# about 4 GB of CUDA libraries. Remove test and header files that the
# server does not use. torch/bin stays: torch needs torch_shm_manager.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    SP=/usr/local/lib/python3.11/site-packages && \
    rm -rf $SP/torch/test $SP/torch/include $SP/torch/lib/*test* && \
    find $SP -name "__pycache__" -type d -prune -exec rm -rf {} +

COPY requirements-cpu.txt .
RUN pip install --no-cache-dir -r requirements-cpu.txt && \
    SP=/usr/local/lib/python3.11/site-packages && \
    find $SP -name "__pycache__" -type d -prune -exec rm -rf {} + && \
    mkdir -p /big/parts && \
    split -b 120M -d -a 1 $SP/torch/lib/libtorch_cpu.so /big/parts/libtorch_cpu.so.part && \
    rm $SP/torch/lib/libtorch_cpu.so && \
    mv $SP/torch /big/torch

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

# The Cloudflare registry drops the connection on layer uploads above
# about 100 MB compressed. The Python packages ship in several layers:
# other packages, torch without its main library, and libtorch_cpu.so
# (440 MB) in four chunks that entrypoint.sh joins on first start.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --from=deps /big/torch /usr/local/lib/python3.11/site-packages/torch
COPY --from=deps /big/parts/libtorch_cpu.so.part0 /parts/
COPY --from=deps /big/parts/libtorch_cpu.so.part1 /parts/
COPY --from=deps /big/parts/libtorch_cpu.so.part2 /parts/
COPY --from=deps /big/parts/libtorch_cpu.so.part3 /parts/

COPY hello_rewards.py server.py unified_hello.py macbeth.json entrypoint.sh ./
COPY templates/ ./templates/

ENV PORT=8000
EXPOSE 8000

CMD ["./entrypoint.sh"]
