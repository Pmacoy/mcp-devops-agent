# syntax=docker/dockerfile:1
#
# Stdlib-only on purpose: this service exists to give the demo more than
# one container to reason about, not to demonstrate a real app framework,
# so there's no dependency surface worth adding.
FROM python:3.12-slim

WORKDIR /app
COPY app.py .

# python:3.12-slim's default user is root; create an unprivileged one
# explicitly. This container doesn't touch anything sensitive, but
# least-privilege shouldn't be conditional on that.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
CMD ["python3", "app.py"]
