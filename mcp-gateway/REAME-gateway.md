## send mail

curl -X POST http://localhost:8087/message \
-H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "send_email",
    "arguments": {
      "to": "khachhang@example.com",
      "subject": "Cập nhật trạng thái Claim #123",
      "body": "<p>Claim của bạn đang được xử lý. Vui lòng kiểm tra lại sau 24h.</p>"
    }
  }
}'

## phone call

curl -X POST http://localhost:8087/message \
-H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "make_phone_call",
    "arguments": {
      "phone_number": "+84901234567",
      "message": "Xin chào, đây là thông báo tự động từ Voice2Claim về vụ việc của bạn."
    }
  }
}'

## in ấn
curl -X POST http://localhost:8087/message \
-H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "print_report",
    "arguments": {
      "claim_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "format": "pdf"
    }
  }
}'

## tìm vector
curl -X POST http://localhost:8087/message \
-H "Content-Type: application/json" \
-d '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_relatives_vector",
    "arguments": {
      "query": "Người thân tên Nguyễn Văn A, liên quan đến xe biển số 59X1-123.45",
      "top_k": 3
    }
  }
}'