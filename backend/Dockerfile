FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_HTTP_TIMEOUT=600
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN echo 'Acquire::http::Timeout "300";' > /etc/apt/apt.conf.d/99timeout \
    && echo 'Acquire::ftp::Timeout "300";' >> /etc/apt/apt.conf.d/99timeout \
    && echo 'Acquire::ForceIPv4 "true";' >> /etc/apt/apt.conf.d/99timeout \
    && apt-get update -y \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-fra \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY init_db.py ./

EXPOSE 8000

CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]