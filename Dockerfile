FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY myrun ./myrun
RUN uv sync --frozen --no-dev
COPY app ./app
COPY .streamlit ./.streamlit
ENV HOME=/tmp MYRUN_CONFIG=/config/config.yaml
EXPOSE 8501
USER 1000:1000
# The launcher is `streamlit run` plus a background thread that keeps the result cache warm.
CMD [".venv/bin/python", "-m", "myrun.ui.warm", "run", "app/Dashboard.py", "--server.address", "0.0.0.0", \
     "--server.port", "8501", "--server.headless", "true", \
     "--browser.gatherUsageStats", "false"]
