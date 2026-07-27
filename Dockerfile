FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies before copying source to leverage layer cache
COPY pyproject.toml uv.lock ./
RUN uv sync --no-group dev

COPY . .

EXPOSE 5000

CMD ["uv", "run", "gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "wsgi:app"]
