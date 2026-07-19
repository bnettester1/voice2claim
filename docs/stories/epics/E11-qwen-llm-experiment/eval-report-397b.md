# Eval Qwen đối chứng — (default config)

```
   A | QWEN     7/7 ✅                9004ms | LOCAL     7/7 ✅               1541ms
   B | QWEN     7/7 ✅                8977ms | LOCAL     7/7 ✅               1476ms
   C | QWEN     9/9 ✅                9313ms | LOCAL     9/9 ✅               1121ms
   D | QWEN     7/9 ✅                7405ms | LOCAL     9/9 ✅               6336ms
   E | QWEN     7/8 ✅                8230ms | LOCAL     8/8 ✅                201ms
   F | QWEN    9/11 ✅                8878ms | LOCAL   11/11 ✅                201ms
   G | QWEN     8/8 ✅                7010ms | LOCAL     8/8 ✅                240ms
   H | QWEN     8/8 ✅                8099ms | LOCAL     8/8 ✅                268ms
   I | QWEN   10/10 ✅                9155ms | LOCAL   10/10 ✅                172ms
   J | QWEN     6/9 ✅                8102ms | LOCAL     9/9 ✅                263ms
 N1q | QWEN     0/0 ✅                3360ms | LOCAL     0/0 ⚠️FP(REQUEST_MOTORBIKE_TOWING)    50ms
 N2q | QWEN     0/0 ✅                3528ms | LOCAL     0/0 ⚠️FP(REQUEST_CAR_TOWING)    49ms
 N3q | QWEN     0/0 ✅                3066ms | LOCAL     0/0 ⚠️FP(ISSUE_ELECTRONIC_PRESCRIPTION)    39ms
 N4q | QWEN     0/0 ✅                2903ms | LOCAL     0/0 ⚠️FP(ISSUE_OUTPATIENT_TREATMENT_ORD)    74ms

QWEN : field 78/86 (90%) · action sạch 14/14 · latency median 8102ms
LOCAL: field 86/86 (100%) · action sạch 10/14 · latency median 240ms
```

- D miss: ["chan_doan: gold='viêm loét tá tràng, ổ loét 1cm mặt trước tá tràng' got='viêm loét tá tràng, test HP dương tính'", "chuyen_khoa: gold='tiêu hóa' got='None'"]
- E miss: ["chuyen_khoa: gold='chấn thương chỉnh hình' got='None'"]
- F miss: ["chan_doan: gold='tăng cholesterol máu, nguy cơ tim mạch' got='LDL-cholesterol cao 3.8 mmol/L, chức năng tim còn tốt EF 60%'", "chuyen_khoa: gold='tim mạch' got='None'"]
- J miss: ['ket_qua_cls 0/1', "tai_kham: gold='sau 2 tuần' got='hai tuần nữa'", "chuyen_khoa: gold='tim mạch' got='None'"]