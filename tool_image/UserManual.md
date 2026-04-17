# Tài Liệu Hướng Dẫn Sử Dụng 

Phần mềm **Tools AI Studio** là giải pháp tối thượng dành riêng cho dân POD (Print-On-Demand) và thiết kế hệ thống cá nhân hóa (Teeinblue, Customily). Phần mềm giúp biến hóa, nâng cấp hoặc phục chế lại các Clipart (nhân vật, tóc, phụ kiện) bị mờ/xấu thành ảnh chất lượng cực cao (4K), đã xóa sạch nền và chuẩn hóa kích thước hàng loạt.

---

## Phần 1: Hướng Dẫn Dụng (User Manual)

### 1. Chuẩn Bị
- Chạy trực tiếp `python clipart_tool.py`.
- **API Key:** Dán mã khóa Google Gemini API Key của bạn vào ô đầu tiên. (Có thể lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/)).

### 2. Các Bước Vận Hành Cơ Bản
**Bước 1: Chọn Thư Mục Chứa Clipart**
- Bấm **Browse** ở mục `Input Folder` và trỏ vào thư mục chứa ảnh Clipart cũ. Toàn bộ ảnh sẽ được quét và xếp vào danh sách bên phải.
- *(Tùy chọn)* Chọn thư mục xuất file ở ô `Output Folder`. Nếu bỏ trống, phần mềm tự tạo thư mục `output` nằm ngay cạnh file gốc.

**Bước 2: Phân Tích (Analyze)**
- Chọn 1 tấm ảnh trong danh sách, bấm nút **Analyze Image**.
- AI sẽ tự động "nhìn" bức ảnh và tự sinh ra một câu lệnh miêu tả chi tiết (Prompt) bắn vào hộp văn bản bên dưới. Câu lệnh này là móng vuốt để AI tái cấu trúc lại ảnh.

**Bước 3: Chọn Chế Độ Sinh Ảnh**
- **Strict Clone (Phục Chế Nguyên Trạng):** Ép AI sao chép y xì đúc cấu trúc, kiểu dáng, tỷ lệ học của bức ảnh gốc. Chỉ nâng cấp độ phân giải lên cực nét và đánh bóng chi tiết.
- **Creative Redesign (Sáng Tạo Không Biên Giới):** AI sẽ dùng bức ảnh gốc làm "phôi" và xào nấu lại cấu trúc bên trong (Ví dụ: Đổi kiểu ống hút, đổi hướng lọn tóc, đổi đồ trang trí) nhưng tuyệt đối không làm trật khớp tỷ lệ kích thước tổng thể.

**Bước 4: Xem Trước & Hàng Loạt**
- Bấm **Preview (1 Image)** để chạy thử trên bức ảnh đang chọn. 
- *Lưu ý: Ngay ở CÚ CLICK ĐẦU TIÊN của một máy tính Mới, phần mềm sẽ "đứng hình" khoảng 1-3 phút để tải ngầm Não bộ Xóa Nền (170MB). Hãy kiên nhẫn! Kể từ tấm thứ 2 trở đi sẽ bay như sấm.*
- Nếu kết quả ưng ý, bấm **Generate All** để máy tự động cày cuốc qua đêm toàn bộ 100-200 bức ảnh trong thư mục.

---

## Phần 2: Luồng Kỹ Thuật Dưới Nền (Technical Workflow)

Dưới đây là bức tranh toàn cảnh về cách 1 bức ảnh được vắt kiệt công suất AI và Python để cho ra thành phẩm:

### 1. Nạp và Xử Lý Hình Học Cơ Sở (Pillow & Numpy)
Hình ảnh Clipart sẽ được thư viện **Pillow (PIL)** quét vào hệ thống. Nếu ảnh gốc có nền trong suốt, phần mềm sẽ dùng thuật toán dập 1 tấm thảm Trắng (#FFFFFF) xuống dưới cùng để bọc lót, giúp hệ thống Gen-AI không bị loạn định dạng.

### 2. Tổng Hợp Ảnh Mới (Google Gemini 1.5/3.0 API via HTTP Requests)
- Gửi ảnh gốc kèm Lệnh Điều Khiển lên lõi AI của Google Gemini (Mô hình `gemini-2.5-flash` / `gemini-3.0-pro`).
- Bằng các "Quy Tắc Thép" (Strict Rules) đã được ghim trong mã nguồn, AI buộc phải xuất ra bức ảnh độ phân giải Max ping, bất chấp rào cản từ tấm ảnh gốc bị mờ/vỡ nét. Lệnh điều khiển ép buộc AI vẽ ảnh lơ lửng trên Bạt Trắng Xóa.

### 3. Debug Từng Giai Đoạn
Sau mỗi lần chạy, tool sẽ lưu ảnh debug theo từng bước trong thư mục `debug/<ten_anh>/`:
- `01_raw_gemini_output.png`: ảnh Gemini trả về nguyên trạng.
- `02_background_removed.png` hoặc `02_background_mask_applied.png`: ảnh sau khi bóc nền / áp alpha mask.
- `03_cropped_object.png`: ảnh sau khi crop sát vật thể.
- `04_scaled_object.png`: ảnh sau khi scale về kích thước mục tiêu.
- `05_final_output.png`: ảnh cuối cùng sau sharpen và ghép canvas.

### 3. Giải Phẫu Kỹ Thuật Số (Rembg & ISNet - Dichotomous Image Segmentation)
**Đây là công đoạn xương sống của Tool:**
Bức hình trả về luôn nằm trên Nền Trắng. Để lấy được vật thể ra, luồng code gọi thư viện **`Rembg`** mang theo khối não **`isnet-general-use`** (Dung lượng 170MB - được lưu trữ qua `pooch` và chạy gia tốc bằng `onnxruntime`).
- Khác với công cụ U2Net cũ (bị cấn bóng trắng ở kẽ hở), mô hình ISNet (2022) chuyên dùng để cắt bóc lông tơ, tóc mây, nan hoa xe đạp. Nó vét sạch mọi hạt sương trắng lẩn khuất giữa các khe lá/chùm tóc.

### 4. Triệt Tiêu Vầng Quang Trắng - Defringing (Alpha Matting)
Sau khi tháo nền, phần mềm chạy qua hàm toán học `alpha_matting`. Nhờ hàm này, viền ngoài cùng của các vật thể thủy tinh hay viền tóc mỏng sẽ bị lột sạch màu trắng do bị loang lổ bởi phản quang của cái Bạt Trắng lúc nãy (Color Bleed Removal). Giữ lại 100% độ lóng lánh trong suốt.

### 5. Căn Chỉnh Ma Trận Hộp Cắt (Numpy Auto-crop)
Dùng ma trận dữ liệu ảnh qua thư viện **`Numpy`** (`np.argwhere(alpha > 0)`). Thuật toán sẽ quét tọa độ điểm ảnh Trái/Phải/Trên/Dưới cùng để xác định Bounding Box (Hộp giới hạn), sau đó cắt xén vứt gọn gàng mọi khoảng trắng thừa không cần thiết.

### 6. Chuẩn Hóa Khung Xương (Teeinblue Normalization Standard)
Tất cả ảnh của dân POD phải Tuân Thủ Cùng 1 Kích Thước để ráp vào Template không bị nhảy phom (Lỗi cọc cạch).
- Dùng phép toán Scale để biến cạnh Tối Đa (Trục lớn nhất) của vật luôn luôn chạm bằng kích thước **Target Size (Ví dụ: 1800px)**.
- Trải 1 tấm màn cực lớn chuẩn **Canvas (2400x2400)** trong suốt.
- Dùng tính toán ma trận để căn thẳng Bức Ảnh vừa phóng to, thả rơi tự do chính giữa (Dead Format Center) tấm Canvas 2400px đó.

### 7. Khử Mờ Sắc Nét Cao Cấp (PIL UnsharpMask Convolution)
Việc kéo kích thước lên 1800px sẽ làm vỡ nét ảnh nhẹ. Hệ thống sẽ càn qua một bộ lọc Bộ nội suy **`ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2)`** siêu mạnh, ép cho các đường cong nổi khối đanh và sắc lẹm, triệt tiêu sương mù Upscale. Cuối cùng bơm thêm 12% màu sắc (Color Enhance) để bản in DTG có màu rực rỡ nhất.

### 8. Gắn Thẻ Chỉ Định Máy In (Save to Disk)
Bức ảnh được nhả xuống ổ cứng tại Thư mục Output nhưng không phải File PNG thường. Nó bị găm thẳng bằng thẻ meta-data **DPI=(300, 300)**. Các máy in áo thun Kỹ thuật số (DTF/DTG) đọc trực tiếp thẻ nhớ này và phun mực đúng chuẩn quốc tế.
