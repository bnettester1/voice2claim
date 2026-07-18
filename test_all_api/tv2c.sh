#!/bin/bash

# ==========================================
# Voice2Claim - API Test Script (Robust Version with Cookie Jar)
# ==========================================

BASE_URL="https://dathoc.net/v2c/api"
AUDIO_FILE="giamdinh_01.wav" # Đảm bảo file này tồn tại ở thư mục bạn chạy script
COOKIE_JAR="/tmp/v2c_cookies.txt" # File lưu cookie giữa các request

# Xóa cookie jar cũ nếu có để đảm bảo sạch sẽ
rm -f "$COOKIE_JAR"

GREEN='\033[1;32m'
RED='\033[1;31m'
CYAN='\033[1;36m'
NC='\033[0m'

print_header() { echo -e "\n${CYAN}==========================================" ; echo "▶️  $1" ; echo "==========================================${NC}\n"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Helper: Thử format JSON, nếu lỗi thì in raw text để debug
safe_json() {
    local output=$(cat)
    if echo "$output" | jq . >/dev/null 2>&1; then
        echo "$output" | jq .
    else
        echo -e "${RED}⚠️ SERVER RETURNED NON-JSON (Raw Response):${NC}"
        echo "$output"
    fi
}

echo -e "${CYAN}🚀 Bắt đầu test API Voice2Claim tại: $BASE_URL${NC}"

# ==========================================
# 1. HEALTH CHECK
# ==========================================
print_header "1. Health Check"
curl -s -X GET "$BASE_URL/health" \
    -H "Origin: https://dathoc.net" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" | safe_json

# ==========================================
# 2. ACTIVATE SESSION (LƯU COOKIE)
# ==========================================
print_header "2. Activate Session (Lấy Token & Lưu Cookie)"
# Dùng -c để lưu cookie vào file COOKIE_JAR
RESPONSE=$(curl -s -c "$COOKIE_JAR" -X POST "$BASE_URL/activate" \
    -H "Content-Type: application/json" \
    -H "Origin: https://dathoc.net" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    -d '{"fingerprint": "test-fp-secure-12345"}')

echo "$RESPONSE" | safe_json

if echo "$RESPONSE" | grep -q '"status":"success"'; then
    print_success "Đã kích hoạt session và lưu cookie thành công!"
else
    print_error "Không thể kích hoạt session. Kiểm tra response ở trên."
    exit 1
fi

# ==========================================
# 3. PROCESS VOICE (All-in-One)
# ==========================================
print_header "3. Process Voice (All-in-One)"
if [ ! -f "$AUDIO_FILE" ]; then
    print_error "Không tìm thấy file audio tại: $AUDIO_FILE"
    print_error "Vui lòng chạy script từ thư mục chứa file audio hoặc chỉnh lại đường dẫn AUDIO_FILE."
    exit 1
fi

print_success "Đang gửi file: $AUDIO_FILE"
# Dùng -b để GỬI cookie đã lưu từ bước 2
curl -s -b "$COOKIE_JAR" -X POST "$BASE_URL/claims/process-voice" \
    -H "Accept-Language: vi" \
    -H "Origin: https://dathoc.net" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    -H "X-Device-Fingerprint: test-fp-secure-12345" \
    -F "audio=@$AUDIO_FILE" \
    -F "template_type=auto_claim" | safe_json

# ==========================================
# 4. GET CLAIMS LIST
# ==========================================
print_header "4. Get Claims List (Lấy danh sách từ DB)"
# Dùng -b để GỬI cookie
curl -s -b "$COOKIE_JAR" -X GET "$BASE_URL/claims" \
    -H "Accept-Language: vi" \
    -H "Origin: https://dathoc.net" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    -H "X-Device-Fingerprint: test-fp-secure-12345" | safe_json

print_header "🎉 HOÀN TẤT TẤT CẢ CÁC TEST!"