FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN echo "Acquire::http::Timeout \"300\";" > /etc/apt/apt.conf.d/99timeout && \
    echo "Acquire::ftp::Timeout \"300\";" >> /etc/apt/apt.conf.d/99timeout && \
    echo "Acquire::ForceIPv4 \"true\";" >> /etc/apt/apt.conf.d/99timeout && \
    apt-get update -y && \
    apt-get install -y --fix-missing \
    python3.11 \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_HTTP_TIMEOUT=600

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

COPY . .

EXPOSE 8000

CMD ["uv", "run", "--frozen", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]