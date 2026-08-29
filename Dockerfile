FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 harness
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
USER harness
EXPOSE 8765
VOLUME ["/data"]
CMD ["agent-harness", "serve", "--db", "/data/agent-harness.db", "--host", "0.0.0.0", "--port", "8765"]
