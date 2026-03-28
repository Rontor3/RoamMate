FROM python:3.13-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Using --no-deps because requirements.txt is a full pip freeze with exact pins.
# This bypasses pip's resolver conflicts (asyncpraw/aiosqlite, langchain-groq/langchain-core).
RUN pip install --no-cache-dir --no-deps -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
