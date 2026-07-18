import os
import psycopg2
import faiss
import numpy as np
from fastapi import FastAPI
from dotenv import load_dotenv
import requests
from typing import List

# ✅ Load .env TRƯỚC
load_dotenv()

EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://e5_embedding:80/embed")
DEFAULT_THRESHOLD = float(os.getenv("DEFAULT_THRESHOLD", "0.85"))
SHORT_QUERY_THRESHOLD = float(os.getenv("SHORT_QUERY_THRESHOLD", "0.60")) # ✅ [MỚI] Ngưỡng cho từ khóa ngắn

app = FastAPI()

DB_CONFIG = {
    "dbname": os.getenv("DB_POSTGRES_NAME", "voice2claim_db"),
    "user": os.getenv("DB_POSTGRES_USER", "admin"),
    "password": os.getenv("DB_POSTGRES_PASS", "admin123UER34sdsf"),
    "host": os.getenv("DB_POSTGRES_HOST", "postgres"),
    "port": os.getenv("DB_POSTGRES_PORT", "5432")
}

print(f"⏳ Đang khởi tạo FAISS Index...")
print(f"📡 EMBEDDING_URL: {EMBEDDING_URL}")
print(f"🎯 DEFAULT_THRESHOLD: {DEFAULT_THRESHOLD}")
print(f"🎯 SHORT_QUERY_THRESHOLD: {SHORT_QUERY_THRESHOLD} (Cho keyword <= 3 chars)")

index = faiss.IndexFlatIP(768)
keyword_mapping = {}

# ... (Giữ nguyên các hàm normalize_embedding, embed_text, embed_batch, build_full_index) ...
def normalize_embedding(emb: np.ndarray) -> np.ndarray:
    """Chuẩn hóa embedding về unit vector"""
    norm = np.linalg.norm(emb)
    if norm > 0:
        return emb / norm
    return emb

def embed_text(text: str) -> np.ndarray:
    """Gọi E5 API để lấy embedding"""
    r = requests.post(EMBEDDING_URL, json={"inputs": text}, timeout=30)
    r.raise_for_status()
    result = r.json()
    
    if isinstance(result, list):
        emb = np.array(result[0], dtype=np.float32)
    elif isinstance(result, dict) and 'embedding' in result:
        emb = np.array(result['embedding'], dtype=np.float32)
    else:
        raise ValueError(f"Unexpected response format: {result}")
    
    return normalize_embedding(emb)

def embed_batch(texts: List[str]) -> np.ndarray:
    """Embed nhiều texts"""
    if not texts:
        return np.array([], dtype=np.float32).reshape(0, 768)
    
    try:
        r = requests.post(EMBEDDING_URL, json={"inputs": texts}, timeout=120)
        r.raise_for_status()
        result = r.json()
        
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
            embeddings = np.array(result, dtype=np.float32)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return embeddings / norms
    except Exception as e:
        print(f"⚠️ Batch embedding failed: {e}, fallback...")
    
    embeddings = []
    for i, text in enumerate(texts):
        try:
            emb = embed_text(text)
            embeddings.append(emb)
        except Exception as e:
            print(f"  ❌ Error text {i}: {e}")
            embeddings.append(np.zeros(768, dtype=np.float32))
    
    return np.array(embeddings, dtype=np.float32)

def build_full_index():
    global index, keyword_mapping
    
    print("📚 Đang load dữ liệu từ database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    items = []
    
    cur.execute("SELECT code, title, COALESCE(description, ''), COALESCE(section, 'basic') FROM courses")
    for row in cur.fetchall():
        code, title, desc, section = row
        items.append({
            "type": "course", "code": code, "title": title,
            "text": f"{title}. {desc}", "section": section
        })
    
    cur.execute("""
        SELECT s.code, s.title, COALESCE(s.description, ''), 
               COALESCE(s.subtitle, ''), c.code, c.section
        FROM skills s JOIN courses c ON s.course_id = c.id
    """)
    for row in cur.fetchall():
        code, title, desc, subtitle, course_code, section = row
        items.append({
            "type": "skill", "code": code, "title": title,
            "text": f"{title}. {subtitle}. {desc}",
            "course_code": course_code, "section": section
        })
    
    cur.execute("""
        SELECT sl.id, sl.title, COALESCE(sl.content, ''), 
               COALESCE(sl.subtitle, ''), s.code, s.title, c.code, c.section
        FROM slides sl
        JOIN skills s ON sl.skill_id = s.id
        JOIN courses c ON s.course_id = c.id
    """)
    for row in cur.fetchall():
        slide_id, title, content, subtitle, skill_code, skill_title, course_code, section = row
        items.append({
            "type": "skill", "code": skill_code, "title": skill_title,
            "text": f"{skill_title}. {title}. {subtitle}. {content}",
            "course_code": course_code, "section": section, "slide_id": slide_id
        })
    
    cur.close()
    conn.close()
    
    print(f"📊 Đã load {len(items)} items")
    
    if len(items) == 0:
        return
    
    texts = [item["text"] for item in items]
    print(f"🔄 Đang embed {len(texts)} texts...")
    embeddings = embed_batch(texts)
    
    norms = np.linalg.norm(embeddings, axis=1)
    print(f"✅ Embedding norms: min={norms.min():.4f}, max={norms.max():.4f}, mean={norms.mean():.4f}")
    if abs(norms.mean() - 1.0) > 0.01:
        print("⚠️  WARNING: Embeddings not normalized! Forcing normalization...")
        embeddings = embeddings / norms[:, np.newaxis]
    
    index.reset()
    index.add(embeddings)
    keyword_mapping = {i: item for i, item in enumerate(items)}
    
    print(f"✅ FAISS Index sẵn sàng: {len(items)} items")

build_full_index()

@app.post("/rebuild")
def trigger_rebuild():
    build_full_index()
    return {"status": "ok", "total_items": len(keyword_mapping)}

@app.get("/semantic-search")
def semantic_search(
    query: str, 
    top_k: int = 10, 
    threshold: float = None,
    search_type: str = "all"
):
    # 1. Xác định Threshold ban đầu
    if threshold is None:
        effective_threshold = DEFAULT_THRESHOLD
        print(f"🎯 Using DEFAULT_THRESHOLD from .env: {effective_threshold}")
    else:
        effective_threshold = threshold
        print(f"🎯 Using threshold from parameter: {effective_threshold}")
    
    # ✅ [LOGIC MỚI] TỰ ĐỘNG HẠ THRESHOLD NẾU KEYWORD QUÁ NGẮN (<= 3 KÝ TỰ)
    query_clean = query.strip()
    if len(query_clean) <= 3 and effective_threshold > SHORT_QUERY_THRESHOLD:
        print(f"⚠️ Keyword quá ngắn ('{query_clean}' - {len(query_clean)} chars). Tự động hạ threshold từ {effective_threshold} xuống {SHORT_QUERY_THRESHOLD}")
        effective_threshold = SHORT_QUERY_THRESHOLD

    print(f"🔍 Search: query='{query}', type={search_type}, threshold={effective_threshold}")
    
    if index.ntotal == 0:
        return {"query": query, "results": [], "threshold_used": effective_threshold}
    
    try:
        q_vec = embed_text(query).reshape(1, -1)
        q_norm = np.linalg.norm(q_vec)
        print(f"📊 Query embedding norm: {q_norm:.4f}")
        if abs(q_norm - 1.0) > 0.01:
            print("⚠️  Query not normalized! Forcing...")
            q_vec = q_vec / q_norm
    except Exception as e:
        return {"query": query, "results": [], "error": str(e)}
    
    distances, indices = index.search(q_vec, min(top_k * 3, index.ntotal))
    
    results = []
    seen_codes = set()
    all_scores = []
    
    for score, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        
        similarity = float(score)
        all_scores.append(similarity)
        
        # 🔴 CHỈ THÊM NẾU >= THRESHOLD
        if similarity < effective_threshold:
            continue
        
        if len(results) >= top_k:
            break
        
        item = keyword_mapping[idx]
        
        if search_type != "all" and item["type"] != search_type:
            continue
        
        if item["code"] in seen_codes:
            continue
        seen_codes.add(item["code"])
        
        results.append({
            "type": str(item["type"]),
            "code": str(item["code"]),
            "title": str(item["title"]),
            "snippet": str(item["text"][:150]),
            "section": str(item.get("section", "basic")),
            "course_code": str(item.get("course_code", "")),
            "similarity": round(similarity, 4)
        })
    
    if all_scores:
        print(f"📊 Scores: max={max(all_scores):.4f}, min={min(all_scores):.4f}, "
              f"threshold={effective_threshold:.4f}, "
              f"above={sum(1 for s in all_scores if s >= effective_threshold)}/{len(all_scores)}, "
              f"returned={len(results)}")
    
    return {
        "query": str(query),
        "results": results,
        "threshold_used": effective_threshold,
        "total_candidates": len(all_scores)
    }

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "index_size": index.ntotal,
        "embedding_service": EMBEDDING_URL,
        "default_threshold": DEFAULT_THRESHOLD,
        "short_query_threshold": SHORT_QUERY_THRESHOLD, # ✅ Thêm vào health check
        "index_type": "IndexFlatIP (cosine similarity)"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
