# proxy_server.py
import os
import time
import httpx
import json
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import uuid
from dotenv import load_dotenv  # <-- THÊM DÒNG NÀY

# Load biến môi trường từ file .env
load_dotenv()

# --- 1. CẤU HÌNH DATABASE TỪ .ENV ---
DB_HOST = os.getenv("DB_POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_POSTGRES_PORT", "5432")
DB_NAME = os.getenv("DB_POSTGRES_NAME", "voice2claim_db")
DB_USER = os.getenv("DB_POSTGRES_USER", "admin")
DB_PASSWORD = os.getenv("DB_POSTGRES_PASS", "admin123xxx")

# Xây dựng chuỗi kết nối (Dùng sync engine cho SQLAlchemy init)
DATABASE_URL = f"postgresql://{DB_POSTGRES_USER}:{DB_POSTGRES_PASS}@{DB_POSTGRES_HOST}:{DB_POSTGRES_PORT}/{DB_POSTGRES_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()

class LLMAuditLog(Base):
    __tablename__ = "llm_audit_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String)
    client_ip = Column(String)
    model = Column(String)
    request_payload = Column(JSON)
    response_payload = Column(JSON)
    status = Column(String)
    latency_ms = Column(Integer)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    is_sensitive = Column(Boolean, default=False)

# Tạo bảng nếu chưa có
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# --- 2. CẤU HÌNH PROXY ---
app = FastAPI(title="BankA/Construction LLM Audit Proxy")

TARGET_LLM_URL = os.getenv("QWEN_API_URL", "xxx")
TARGET_API_KEY = os.getenv("QWEN_API_KEY", "xxx")

SENSITIVE_KEYWORDS = ["mật khẩu", "password", "cmnd", "cccd", "số tài khoản", "stk", "bí mật"]

def check_sensitive_data(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in SENSITIVE_KEYWORDS)

# --- 3. ENDPOINT CHÍNH ---
@app.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request, x_user_id: str = Header("unknown_user")):
    start_time = time.time()
    client_ip = request.client.host
    
    try:
        payload = await request.json()
        model = payload.get("model", "unknown")
        
        full_prompt = json.dumps(payload.get("messages", []))
        is_sensitive = check_sensitive_data(full_prompt)
        
       if is_sensitive:
            print(f"⚠️ CẢNH BÁO: Phát hiện dữ liệu nhạy cảm từ user {x_user_id}")

        headers = {
            "Authorization": f"Bearer {TARGET_API_KEY}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(TARGET_LLM_URL, json=payload, headers=headers)
            response.raise_for_status()
            response_data = response.json()
   latency_ms = int((time.time() - start_time) * 1000)
        usage = response_data.get("usage", {})
        
        log_entry = LLMAuditLog(
            user_id=x_user_id,
            client_ip=client_ip,
            model=model,
            request_payload=payload,
            response_payload=response_data,
            status="SUCCESS",
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            is_sensitive=is_sensitive
        )
        
        db = SessionLocal()
        db.add(log_entry)
        db.commit()
        db.close()

        return JSONResponse(content=response_data)

    except httpx.HTTPStatusError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        _log_error(x_user_id, client_ip, payload, str(e), latency_ms)
        raise HTTPException(status_code=e.response.status_code, detail="LLM Provider Error")
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        _log_error(x_user_id, client_ip, payload, str(e), latency_ms)
        raise HTTPException(status_code=500, detail=f"Internal Proxy Error: {str(e)}")

def _log_error(user_id, ip, payload, error_msg, latency):
    db = SessionLocal()
    log_entry = LLMAuditLog(
        user_id=user_id, client_ip=ip, model="error",
        request_payload=payload, response_payload={"error": error_msg},
        status="FAILED", latency_ms=latency, is_sensitive=False
    )
    db.add(log_entry)
    db.commit()
    db.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HTTP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
