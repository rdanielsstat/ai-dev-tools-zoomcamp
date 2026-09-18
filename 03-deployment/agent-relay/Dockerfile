FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first so this layer is cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8000

# --host 0.0.0.0 is required: uvicorn's default of 127.0.0.1 only accepts
# connections from inside the container, which makes `docker run -p` look
# broken even though the port mapping itself is fine.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
