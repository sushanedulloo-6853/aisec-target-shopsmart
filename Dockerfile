FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY shopsmart ./shopsmart
COPY data/policies ./data/policies
COPY static ./static
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 app \
    && mkdir -p data/chroma logs \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "python -m shopsmart.seed && uvicorn shopsmart.main:app --host 0.0.0.0 --port 8000"]
