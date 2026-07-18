FROM python:3.10-slim

# Chống Python buffer output (log realtime) và tạo file .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=8 \
    MKL_NUM_THREADS=8

WORKDIR /app

# Cài curl để healthcheck + lib cần thiết cho faiss/numpy
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies trước (tận dụng Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY search.py .

EXPOSE 8000

# Healthcheck đảm bảo FAISS index đã build xong
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "search:app", "--host", "0.0.0.0", "--port", "8000"]