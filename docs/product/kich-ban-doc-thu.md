# Kịch bản đọc thử — Claim bảo hiểm (test mic thật)

Cách test: mở `http://localhost:8321` → pack **🛡️ Bảo hiểm** → tab **📞 Live Call**
→ bấm **"Bắt đầu cuộc gọi"** → đọc kịch bản (một mình đóng cả 2 vai, đổi giọng
nhẹ cho vui). **Mẹo đọc:** chậm vừa phải, rõ chữ; nghỉ ~1 giây sau mỗi lượt
thoại (silero-VAD sẽ tự chốt câu); câu trigger "bấm nút…" đọc liền nguyên cụm.
Xong bấm **Kết thúc** → tab **✅ Duyệt & Gửi** → xem điểm → **GỬI FORM ĐI** →
tab **🗄️ Console** xem ticket + mở PDF.

(Có thể test qua tab 📁 Xử lý ghi âm: bấm 🎙️ Ghi âm, đọc, bấm Dừng — kết quả
tương tự nhưng chờ ASR batch ~10–15s.)

---

## Kịch bản 1 — "SH Mode quận 10" (~60 giây, dễ, 1 action auto)

> **GĐV:** Alô, em chào chị Thảo, em là giám định viên bảo hiểm. Em nhận được
> thông báo xe chị vừa gặp sự cố trên đường Ba Tháng Hai, quận 10, lúc khoảng
> tám giờ sáng nay đúng không ạ?
>
> **Khách:** Đúng rồi em ơi. Chị đang chở con đi học thì bị một chiếc Kia
> Seltos màu đỏ, biển số năm mốt ca, sáu trăm bảy mươi tám chấm chín mươi, tạt
> đầu. Chị thắng gấp nên trượt bánh ngã ra đường.
>
> **GĐV:** Dạ em chia sẻ với chị. Xe của chị là xe gì, biển số bao nhiêu ạ?
>
> **Khách:** Xe chị là Honda SH Mode màu trắng, biển số năm chín ích hai,
> ba trăm bốn mươi lăm chấm sáu mươi bảy. Số giấy chứng nhận bảo hiểm của chị
> là BH hai không hai bốn, không chín một hai ba bốn.
>
> **GĐV:** Dạ. Xe mình hư hỏng những gì chị nhìn thấy được ạ?
>
> **Khách:** Vỡ nguyên dàn áo bên phải nè, cong tay lái, với bể cái đèn xi
> nhan trước. Chị thì trầy khuỷu tay thôi, con chị ngồi sau không sao. À chị
> có clip camera hành trình của xe chạy phía sau quay lại được nha.
>
> **GĐV:** Dạ quá tốt. Em ghi nhận đầy đủ rồi. Chị giữ nguyên hiện trường,
> và **bấm vào nút Gửi yêu cầu cứu hộ xe máy** giúp em nhé, xe cứu hộ sẽ tới
> trong khoảng hai mươi phút.
>
> **Khách:** OK em, chị bấm liền đây.

**Kỳ vọng:** tên *Thảo* · vị trí *đường Ba Tháng Hai, quận 10* · thời điểm
*~8h sáng* · số GCN *BH-2024-091234* (ITN từ số đọc chữ) · xe khách *SH Mode*
· biển số *59X2-345.67* · xe liên quan *Kia Seltos — 51K-678.90* · hư hỏng 3
mục · thương tích *trầy khuỷu tay* · bằng chứng *clip camera hành trình* ·
⚡ `REQUEST_MOTORBIKE_TOWING` **ARMED khi đang nói → tự FIRE** → ticket + PDF
+ giọng agent đáp. Score dự kiến ≥90.

---

## Kịch bản 2 — "Liên hoàn cầu vượt" (~90 giây, khó: 3 xe + người bị thương + 2 action)

> **GĐV:** Alô, anh Đạt phải không ạ? Em là giám định viên hiện trường. Em
> được báo có vụ va chạm liên hoàn ở cầu vượt Hàng Xanh, anh mô tả giúp em với.
>
> **Khách:** Rối lắm em ơi. Xe anh là Mazda 3, biển số năm mốt hát, một trăm
> hai mươi ba chấm bốn lăm. Anh đang đổ dốc cầu thì chiếc Grab SH biển năm
> chín tê một, tám trăm tám mươi tám chấm hai hai thắng không kịp tông vào
> đuôi xe anh, đẩy xe anh dồn lên đâm vào chiếc Innova biển sáu mươi a,
> bốn trăm năm mươi sáu chấm bảy tám phía trước.
>
> **GĐV:** Dạ vậy là ba phương tiện. Xe anh hư hỏng thế nào ạ?
>
> **Khách:** Đuôi xe anh móp nặng, bể đèn hậu bên trái, còn đầu xe thì móp
> ca-pô với nứt cản trước. Cái xe Innova phía trước bị móp cửa cốp sau.
>
> **GĐV:** Có ai bị làm sao không anh?
>
> **Khách:** Cậu chạy Grab bị ngã, đang ngồi lề đường ôm cổ tay, kêu đau,
> chắc bong gân. Anh với người trên Innova thì không sao.
>
> **GĐV:** Dạ, an toàn là trên hết. Trước tiên em sẽ **xác nhận có người bị
> thương** trên hệ thống để kích hoạt quy trình y tế nhé anh.
> *(nghỉ 2 giây — nút CONFIRM_PERSONAL_INJURY tự sáng và FIRE)*
> Rồi, anh chụp ảnh toàn cảnh ba xe, xong anh **bấm nút gửi biên bản va chạm
> liên hoàn** để bên pháp chế xử lý sớm nhất giúp em.
>
> **Khách:** OK, anh làm ngay.

**Kỳ vọng:** 3 xe tách đúng (*Mazda 3 — 51H-123.45* là xe khách; list xe liên
quan: *SH — 59T1-888.22*, *Innova — 60A-456.78*) · hư hỏng xe khách 4 mục ·
hư hỏng xe liên quan (cửa cốp Innova) · thương tích *tài xế Grab đau cổ tay
nghi bong gân* → **priority CAO** · ⚡ `CONFIRM_PERSONAL_INJURY` auto-fire ·
🖐️ `SUBMIT_MULTI_VEHICLE_COLLISION_REPORT` **chỉ ARMED (vàng, chờ bấm)** vì
là action policy *click* — bấm nút trên UI hoặc để qua màn Duyệt. Đây là chỗ
khoe "action khẩn tự chạy, hồ sơ thì người quyết".

---

## Kịch bản 3 — "Nói lộn xộn có sửa lời" (~40 giây, stress test đúng đề bài)

> **Khách:** Alô alô, em hả, chị Hương nè. Ừm… xe chị á, cái Vision đó, bị
> quẹt ở… chỗ vòng xoay Phú Lâm á. Hồi nãy, cỡ ba giờ chiều. Cái ông SantaFe
> biển năm mốt xê… à khoan, nhầm, **năm mốt gờ** chứ, năm mốt gờ ba trăm hai
> mươi mốt chấm không chín, ổng de trúng xe chị. Bể yếm, gãy kính chiếu hậu
> phải. Chị hông sao, đừng lo. Em check camera cây xăng kế bên là thấy liền
> á. Thôi em **gửi yêu cầu cứu hộ xe máy** giùm chị nha.

**Kỳ vọng:** hệ thống lấy biển số **bản đã sửa lời** (*51G-321.09*, không phải
51C) · vị trí *vòng xoay Phú Lâm* · thời điểm *~15h* · code-switch "check
camera" giữ nguyên · bằng chứng *camera cây xăng* · towing ARMED→FIRE dù câu
trigger nói tắt (không có chữ "bấm nút"). Field nào máy nghe mơ hồ sẽ tô
vàng + NER cảnh báo — đúng chỗ demo màn Duyệt.

---

## Checklist chấm nhanh (nhìn ở đâu)

1. **Transcript** chạy chữ mờ (partial) → chốt đậm (final) ngay khi đang nói.
2. **Form** điền dần từ ~giây thứ 9, viền xanh/vàng theo confidence, tooltip
   evidence là câu trích đúng lời anh vừa đọc.
3. **Nút action**: vàng nhấp nháy = ARMED (kèm badge độ trễ ms), ✅ = FIRED
   (nghe luôn giọng agent đáp).
4. **Duyệt & Gửi**: vòng điểm + mục "Cần chú ý" (nếu đọc nhanh/nuốt số, biển
   số sai định dạng sẽ bị gắn cờ đỏ — sửa tay rồi gửi).
5. **Console**: ticket mới + priority + webhook log; bấm 📄 mở PDF kiểm tra
   dấu tiếng Việt + đoạn "Tóm tắt diễn biến".
