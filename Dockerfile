# Stage 1: build the React workspace
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY modern-workspace/package.json modern-workspace/package-lock.json ./
RUN npm ci
COPY modern-workspace/ ./
RUN npm run build

# Stage 2: gateway + static app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8790 \
    GATEWAY_CONFIG=/data/gateway_config.json \
    DB_PATH=/data/gateway.db
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway.py api_pool.py ./
COPY --from=frontend-build /build/dist ./static
RUN mkdir -p /data /workspace
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/health', timeout=3)"
CMD ["python", "gateway.py"]