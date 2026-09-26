FROM python:3.12.11-slim-bookworm

ARG EMBEDDING_PROVIDER=gemini
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/asklaw/huggingface \
    EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER} \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}

WORKDIR /app

RUN groupadd --system asklaw \
    && useradd --system --gid asklaw --home-dir /app --shell /usr/sbin/nologin asklaw

COPY requirements.txt ./requirements.txt
COPY requirements-gemini.txt ./requirements-gemini.txt
COPY docker/constraints-cpu.txt ./docker/constraints-cpu.txt

RUN if [ "${EMBEDDING_PROVIDER}" = "gemini" ]; then \
        python -m pip install --no-cache-dir \
            --constraint requirements.txt \
            -r requirements-gemini.txt; \
    elif [ "${EMBEDDING_PROVIDER}" = "local" ]; then \
        python -m pip install --no-cache-dir \
            --extra-index-url "${PYTORCH_CPU_INDEX_URL}" \
            --constraint docker/constraints-cpu.txt \
            -r requirements.txt; \
    else \
        echo "Unsupported EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER}" >&2; \
        exit 2; \
    fi

# Only the local-provider image contains PyTorch/SentenceTransformer and the
# cached model. Gemini images avoid those packages and model weights entirely.
RUN if [ "${EMBEDDING_PROVIDER}" = "local" ]; then \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"; \
        chmod -R a+rX /opt/asklaw/huggingface; \
    fi

COPY app ./app
COPY docker/api_healthcheck.py docker/mcp_healthcheck.py ./docker/

RUN chown -R asklaw:asklaw /app

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER asklaw

EXPOSE 8000 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
