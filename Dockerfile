# worm-ai — Hugging Face Space image (Docker SDK, serves on port 7860)
# © 3MH Technologies — https://3mh.pages.dev/ — t.me/j49_c
FROM python:3.13-slim
FROM python:3.13-slim

RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get upgrade -y ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

COPY --chown=user package.json package-lock.json ./
COPY --chown=user apps/web/package.json ./apps/web/
COPY --chown=user apps/api/pyproject.toml ./apps/api/

RUN npm ci && pip install --no-cache-dir -e apps/api/

COPY --chown=user . .

RUN npm run build --workspace=apps/web

EXPOSE 7860

ENV PORT=7860 \
    NEXT_PUBLIC_API_URL=http://localhost:8000

CMD ["sh", "-c", "(cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000) & (cd apps/web && npx next start -H 0.0.0.0 -p $PORT) & wait"]
