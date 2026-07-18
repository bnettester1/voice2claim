# Sử dụng image Python nhẹ và bảo mật cho production
FROM python:3.11-slim

# Thiết lập biến môi trường tối ưu cho Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Đặt thư mục làm việc
WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết (ví dụ: để build psycopg2)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Expose port mặc định của FastAPI
EXPOSE 8000

# Lệnh mặc định (sẽ bị override bởi docker-compose)
CMD ["uvicorn", "proxy_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
