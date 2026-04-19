# Use Python slim image
FROM python:3.12-slim

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml README.md ./
COPY uv.lock* ./

# Install dependencies using uv
RUN uv sync --frozen || uv sync

# Copy application code
COPY . .

# Run the application
CMD ["uv", "run", "python", "app.py"]
