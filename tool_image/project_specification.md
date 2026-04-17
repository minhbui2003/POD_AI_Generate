# Phân Tích & Đặc Tả Bài Toán (Project Specification)

## 1. Tên Gọi Của Bài Toán Trong Ngành (Industry Terms)
Nếu bạn rảnh rỗi dạo qua Google hoặc Github để tìm các công cụ có sẵn nhằm xử lý riêng biệt được việc này, hãy thử các từ khóa chuyên ngành rọng sau:
- **Batch Image-to-Image ControlNet Pipeline**: Xử lý đồ họa dựa theo mẫu gốc (Dùng Stable Diffusion).
- **POD Asset Variations Generator**: Công cụ tự động đẻ ra các biến thể thiết kế dùng riêng cho mảng POD (Print-on-Demand).
- **Automated Clipart Restyling Tool**: Công cụ tái tạo hoa văn/phong cách Clipart tự động.
- **AI Transparent Background Batch Processor**: Tách nền trong suốt với số lượng lớn.

> LƯU Ý QUAN TRỌNG:
> Thực tế hiện nay rất ít Tool thương mại nào trên thị trường làm chuẩn xác được yếu tố **"Khóa Cứng Form Dáng Cắt Ghép" (Pixel-perfect Bounding Box Layering)**. Các nền tảng AI như Midjourney, ChatGPT hay Leonardo chỉ quen vẽ ra cả 1 bối cảnh lớn. Còn việc chia tách từng Mảnh ghép rỗng nền (Layer cái ly, layer mái tóc, layer quần áo riêng biệt) nhưng ĐẢM BẢO khớp tọa độ để tự động gắn đè lên nhau như búp bê giấy thì buộc phải Can thiệp Code Toán Học - như cách Tool của chúng ta đang làm.

---

## 2. Mô Tả Bối Cảnh Bài Toán (Context)
Trong mô hình Sản phẩm Cá nhân hóa (Personalized E-Commerce/POD), khách hàng tự thiết kế mẫu mã trên web (VD: Đổi kiểu tóc nhân vật, lồng thêm nón cối, đổi cái ly trà sữa sang nước trái cây).
Hệ thống đồ họa phải duy trì hàng trăm nghìn mẫu Clipart nhỏ lẻ (`.PNG` tàng hình, không có nền). Chúng được đặt đúng chung một Tọa độ Canvas trong bộ hồ sơ Photoshop. Khi thay đổi thuộc tính, chỉ việc Tắt/Mở một cái là nhân vật thay đồ.

Mỗi khi cửa hàng muốn chạy Dịp Lễ mới (như Halloween, Giáng Sinh), Designer phải hì hục sửa lại họa tiết từng layer cái quần, cái áo, cái mắt kính cho hợp chủ đề. Nó ngốn cả ngàn giờ công sức. Bài toán này ép buộc phải có một Bot Xưởng Máy dùng AI càn quét và tái dựng đồ họa hàng loạt nhưng vẫn giữ đúng Form Khuôn Mẫu cũ.

---

## 3. Khối Chức Năng Tool Chuyên Dụng (The Automation Pipeline)

Cắt nghĩa cụ thể từng module mà App Desktop này đảm nhận:

### Khối Nhập Liệu (Inputs Variables)
Xây dựng một Tool yêu cầu truyền vào:
1. **Target Folder**: Một thư mục nội bộ chứa **hàng trăm file ảnh Clipart** định dạng `PNG` (với những khoảng rỗng Alpha tàng hình). Những ảnh này mang kết cấu khối viền đen của Artist nguyên bản.
2. **Parameters (Tham số tinh chỉnh AI)**: Đoạn Text do nghệ sĩ nhúng vào GUI để chi phối não bộ AI (VD: "Đổi màu chất liệu sang đỏ Red, đính cườm, phong cách dạ hội...").
3. **API Tunnel**: Token hợp lệ nối mạng cho Mô hình siêu dữ liệu Google Gemini 2.0.

### Khối Xử Lý Cơ Học (Processing Loop)
Ứng dụng sử dụng đa luồng (Multi-threading) bắt đầu một vòng lặp vắt kiệt hàng loạt:

**Giai đoạn 1: Chuẩn Bị File (Pre-Processing)**
- Lôi từng File PNG rỗng ra. Lập trình Python sẽ ép lót phía dưới nó 1 khối `PANEL MÀU TRẮNG (#FFFFFF)`. Bởi vì AI dị ứng nghiêm trọng và thường xuyên gặp ảo giác nếu ép nó vẽ khoảng Không/Tàng Hình.

**Giai đoạn 2: Lệnh Kỷ Luật (Strict Prompting)**
- Bơm Cấu trúc Prompt chặt đứt mọi sự sáng tạo vô kỷ luật của AI: *"Chỉ tái lập họa tiết nhân vật. CẤM VẼ thêm bóng râm. Cấm phản chiếu mặt đất. Ép nằm cô lập trên nền màu TRẮNG."*

**Giai đoạn 3: Phẫu Thuật Đồ Họa Cắt Gọt Hậu Kỳ (Post-Processing Pixel Math)**
- Ảnh trả về từ AI là 1 cục vuông 1024x1024 khổng lồ bị dính khối phông Trắng ngắc ngoải.
- **Tẩy màu (Floodfill Masking):** AI làm đổ 1 tuýp hóa chất vô hình (Threshold = 70) châm từ 4 mốc góc tấm ảnh để bào rỗng khối mảng nhựa Trắng mà vẫn bảo toàn vật thể.
- **Dò Tìm Giao Diện (Bounding Box Tracker):** Quét tia X toàn bộ ma trận vật thể lấy ra 4 điểm Khung ngoài rìa của cái Ly/Tóc. 
- **Overscale Plumping**: Phơi khô ảnh và kéo giãn toàn cục (phình to thêm 2-3%) cho mọi mép rìa bị rung lệch phải dão ra phía ngoài.
- **Dao Thớt Cookie-Cutter (Alpha Merge)**: Bê nguyên lõi Kênh Tàng Hình (Alpha channel) của chính cái hình Clipart mẫu gốc lúc nãy, chụp mạnh xuống cắt tỉa cục AI. Loại bỏ rụng rời hơn tất cả mọi cái dằm sọc cưa (Jagged edges), viền mỡ tăm trắng ló ra.

### Khối Kết Xuất (Outputs Deliverables)
Sau khi chu trình đi qua vỏn vẹn trong vài giây, thư mục máy tính chào đón:
- Cùng lúc hàng loạt các phiên bản ảnh `.PNG` Repaint hoàn toàn mới!
- Chúng hoàn toàn giữ được tính **Tàng Hình Khung Nền**.
- Khóa khuy cứng nhắc các viền đen ngoài cùng, cắt bo quanh không dính một tì vết dơ xọc dừa hay halo nào.
- **Giá Trị Tuyệt Mật**: Khớp tọa độ xếp lớp tuyệt đối 1:1. Chồng cái File Tóc Gen bằng AI này lên cái ảnh Mái Tóc Cũ trên con búp bê Mẹ thì nó sẽ trùm lên trùng khít 100% đến từng điểm chấm ảnh nhỏ nhất. Mang thẳng vào xưởng xài ngay lập tức.
