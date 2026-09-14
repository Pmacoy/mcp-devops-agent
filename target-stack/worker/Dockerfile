# syntax=docker/dockerfile:1
FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir redis==5.0.8

COPY worker.py healthcheck.py ./

# /tmp is already world-writable (mode 1777) in the base image, so
# appuser (below) can write the heartbeat file there without any extra
# chown -- the HEARTBEAT_FILE default in worker.py/healthcheck.py relies
# on exactly that.
RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["python3", "worker.py"]
