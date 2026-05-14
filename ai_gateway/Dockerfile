FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace/ai_gateway

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

COPY tender_ai_gateway ./tender_ai_gateway
RUN pip install -e . --no-deps --no-build-isolation

EXPOSE 8100

CMD ["uvicorn", "tender_ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8100"]
