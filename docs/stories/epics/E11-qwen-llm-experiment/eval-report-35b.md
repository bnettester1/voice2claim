# Eval Qwen đối chứng — qwen3.5-35b-a3b

```
   A | QWEN     7/7 ✅                5980ms | LOCAL  (skip local)
   B | QWEN     7/7 ✅                6303ms | LOCAL  (skip local)
   C | QWEN     9/9 ✅                6863ms | LOCAL  (skip local)
   D | QWEN     7/9 ⚠️FP(PRINT_EXAMINATION_SLIP_AND_PRE)   6578ms | LOCAL  (skip local)
   E | QWEN     8/8 ✅                9776ms | LOCAL  (skip local)
   F | QWEN    9/11 ✅                7872ms | LOCAL  (skip local)
   G | QWEN     8/8 ✅                7529ms | LOCAL  (skip local)
   H | QWEN     8/8 ✅                8301ms | LOCAL  (skip local)
   I | QWEN   10/10 ✅                9362ms | LOCAL  (skip local)
   J | QWEN     6/9 ✅                6761ms | LOCAL  (skip local)
 N1q | QWEN     0/0 ✅                3137ms | LOCAL  (skip local)
 N2q | QWEN     0/0 ✅                4308ms | LOCAL  (skip local)
 N3q | QWEN     0/0 ✅                3166ms | LOCAL  (skip local)
 N4q | QWEN     0/0 ✅                2859ms | LOCAL  (skip local)

QWEN : field 79/86 (91%) · action sạch 13/14 · latency median 6761ms
```

- D miss: ["chan_doan: gold='viêm loét tá tràng, ổ loét 1cm mặt trước tá tràng' got='viêm loét tá tràng, test HP dương tính'", "chuyen_khoa: gold='tiêu hóa' got='None'"]
- F miss: ["chan_doan: gold='tăng cholesterol máu, nguy cơ tim mạch' got='chức năng tim còn tốt, LDL-cholesterol cao hơn mục tiêu'", "chuyen_khoa: gold='tim mạch' got='None'"]
- J miss: ['ket_qua_cls 0/1', "tai_kham: gold='sau 2 tuần' got='hai tuần nữa'", "chuyen_khoa: gold='tim mạch' got='None'"]