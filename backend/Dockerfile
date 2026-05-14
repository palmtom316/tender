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

# Install third-party dependencies from metadata only. Source code is copied
# later and bind-mounted in local Compose, so ordinary source edits no longer
# invalidate the expensive dependency-download layer.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip setuptools wheel \
    && python - <<'PY' > /tmp/requirements.txt
import tomllib
from pathlib import Path
project = tomllib.loads(Path('pyproject.toml').read_text())['project']
for dep in project.get('dependencies', []):
    print(dep)
for dep in project.get('optional-dependencies', {}).get('dev', []):
    print(dep)
PY
RUN pip install -r /tmp/requirements.txt

COPY tender_backend ./tender_backend
RUN pip install -e . --no-deps --no-build-isolation

EXPOSE 8000

CMD ["uvicorn", "tender_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
