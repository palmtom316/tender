FROM python:3.12-slim

# System dependencies:
#   libreoffice-* — convert legacy .doc / .wps / .xls to docx/xlsx so
#     services/office_document_parser._convert_with_libreoffice works.
#   fonts-noto-cjk — required by libreoffice headless for Chinese text rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-core \
        libreoffice-writer \
        libreoffice-calc \
        fonts-noto-cjk \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace/backend

# Copy package + project metadata so `pip install -e .[dev]` resolves the
# package layout. At runtime the source is overlaid via a bind mount; the
# editable install's .pth in site-packages still points at /workspace/backend,
# so the mounted source is what gets imported.
COPY pyproject.toml README.md ./
COPY tender_backend ./tender_backend

RUN pip install --upgrade pip && pip install -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "tender_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
