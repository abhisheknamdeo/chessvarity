# Dukes Mate AI: web app + Stockfish in one small image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Stockfish from Debian (installed at /usr/games/stockfish).
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# Run as an unprivileged user; all state lives in /data (mount a volume there).
RUN useradd --create-home coach && mkdir /data && chown coach /data
USER coach

ENV STOCKFISH_PATH=/usr/games/stockfish \
    CHESSCOACH_DATA=/data

VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status == 200 else 1)"

CMD ["chesscoach-serve", "--host", "0.0.0.0", "--port", "8000"]
