FROM python:3.12.11-slim-bookworm

ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/asklaw/huggingface \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}

WORKDIR /app

RUN groupadd --system asklaw \
    && useradd --system --gid asklaw --home-dir /app --shell /usr/sbin/nologin asklaw

COPY requirements.txt ./requirements.txt
COPY docker/constraints-cpu.txt ./docker/constraints-cpu.txt

RUN python -m pip install --no-cache-dir \
    --extra-index-url "${PYTORCH_CPU_INDEX_URL}" \
    --constraint docker/constraints-cpu.txt \
    -r requirements.txt

# Cache the exact model artifact in the image. Runtime containers are placed in
# offline mode below so a restart never silently depends on Hugging Face being
# reachable. Rebuilding the image is the deliberate model-refresh operation.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')" \
    && chmod -R a+rX /opt/asklaw/huggingface

COPY app ./app
COPY docker/api_healthcheck.py docker/mcp_healthcheck.py ./docker/

RUN chown -R asklaw:asklaw /app

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER asklaw

EXPOSE 8000 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
