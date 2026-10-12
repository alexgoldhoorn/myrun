FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY myrun ./myrun
RUN uv sync --frozen --no-dev
COPY app ./app
ENV HOME=/tmp MYRUN_CONFIG=/config/config.yaml
EXPOSE 8501
USER 1000:1000
CMD [".venv/bin/streamlit", "run", "app/Now.py", "--server.address", "0.0.0.0", \
     "--server.port", "8501", "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
