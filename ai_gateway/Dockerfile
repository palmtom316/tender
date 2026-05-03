FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace/ai_gateway

COPY pyproject.toml README.md ./
COPY tender_ai_gateway ./tender_ai_gateway

RUN pip install --upgrade pip && pip install -e ".[dev]"

EXPOSE 8100

CMD ["uvicorn", "tender_ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8100", "--reload"]
