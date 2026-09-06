FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir uv==0.10.8
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY frontend ./frontend
EXPOSE 8501
CMD ["uv", "run", "--no-sync", "streamlit", "run", "frontend/main.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
