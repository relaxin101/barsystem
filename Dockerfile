FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies before copying source to leverage layer cache
COPY pyproject.toml uv.lock ./
RUN uv sync --no-group dev

COPY . .

# .git is dockerignored, so utils/version.py can't read it from inside the
# container — pass the commit in explicitly at build time instead.
ARG GIT_SHA=unknown
ENV APP_VERSION=$GIT_SHA

EXPOSE 5000

CMD ["uv", "run", "gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
