# Chiến Lược Chunking Theo Từng Loại Tài Liệu Doanh Nghiệp

Tài liệu này đề xuất chiến lược chunking ban đầu cho 5 nhóm tài liệu trọng tâm trong hệ thống RAG Enterprise (`NDQuynh259/ragflow-api`). Các chiến lược và tham số dưới đây là giả thuyết cấu hình cần được kiểm chứng trên dữ liệu thực tế, không phải cấu hình tối ưu đã được đảm bảo.
1. **Tài liệu nội bộ** (Wiki, Thông báo, Chính sách chung)
2. **Kế hoạch kinh doanh** (Business Plans, Chiến lược, Ngân sách)
3. **Báo cáo tiến độ** (Progress Reports, Sprint / KPI tracking)
4. **Điều khoản dịch vụ** (Terms of Service, Hợp đồng, Quy chế pháp lý)
5. **Tài liệu hướng dẫn** (User Guides, SOPs, Quy trình thao tác chuẩn)

---

## 1. Phân Tích Chi Tiết 5 Loại Tài Liệu Doanh Nghiệp

| Loại tài liệu | Đặc điểm thường gặp | Thách thức trong RAG | Chiến lược khởi đầu (cần kiểm chứng) |
| :--- | :--- | :--- | :--- |
| **1. Kế hoạch kinh doanh & Báo cáo tiến độ** | Có thể chứa bảng ngân sách/KPI, biểu đồ, cùng phần thuyết minh dạng văn xuôi. | Mất header, đơn vị hoặc chú thích khiến số liệu khó hiểu; biểu đồ có thể chứa thông tin không có trong văn bản. | Chunking nhận biết cấu trúc: giữ ngữ cảnh bảng và xử lý biểu đồ khi cần; dùng reading order như một tín hiệu liên kết. |
| **2. Điều khoản dịch vụ (ToS / Quy chế pháp lý)** | Thường có cấu trúc `Chương > Điều > Khoản > Điểm`, đôi khi có bảng hoặc phụ lục. | Cắt qua điều kiện, ngoại lệ, định nghĩa hoặc phần dẫn chiếu có thể làm đổi nghĩa. | Ưu tiên ranh giới section và breadcrumb; chỉ chia nhỏ section quá dài tại ranh giới con phù hợp, giữ liên kết tới phần liên quan. |
| **3. Tài liệu hướng dẫn (User Guide, SOP, Quy trình)** | Có các bước tuần tự, đôi khi kèm screenshot, cảnh báo hoặc ghi chú. | Hình minh họa có thể bị tách khỏi bước liên quan; thứ tự trích xuất không phải lúc nào cũng đúng. | Giữ bước, cảnh báo và hình liên quan trong cùng ngữ cảnh khi quan hệ được xác định đáng tin cậy; lưu tham chiếu hình. |
| **4. Tài liệu nội bộ chung (Wiki, Thông báo, Chính sách)** | Thường là văn xuôi theo chủ đề và đề mục; đôi khi có bảng, danh sách hoặc hình. | Chunk quá nhỏ/mất ngữ cảnh hoặc quá lớn/nhiễu chủ đề. | Hybrid semantic kết hợp ranh giới đề mục/đoạn, sau đó hiệu chỉnh theo kết quả truy hồi. |

---

## 2. Bảng/Ảnh Liên Quan Đến Đoạn Văn Nào Trong Các Tài Liệu Này?

Trong nhiều tài liệu, bảng, biểu đồ hoặc ảnh được đặt gần phần văn bản giải thích, nhưng không thể coi vị trí gần nhau là bằng chứng chắc chắn về quan hệ ngữ nghĩa. PDF nhiều cột, thứ tự đọc sai, chú thích ở trang khác, tham chiếu chéo và bố cục phức tạp có thể làm sai lệch liên kết.

* **Kế hoạch kinh doanh & báo cáo tiến độ:** dùng caption, nhãn, vị trí và tham chiếu trong văn bản làm tín hiệu liên kết; nếu tín hiệu không đủ tin cậy, giữ phần tử riêng nhưng bảo toàn metadata và nguồn/trang.
* **Tài liệu hướng dẫn:** ghép screenshot với bước hướng dẫn khi cấu trúc hoặc tham chiếu hình xác nhận quan hệ đó; không mặc định ảnh ngay dưới là ảnh của bước ngay trước.
* **Điều khoản dịch vụ:** giữ cấu trúc `Điều > Khoản`, đồng thời lưu các tham chiếu chéo và phụ lục liên quan.

> [!NOTE]
> Reading order trong cùng section là một heuristic hữu ích, không phải cam kết luôn chính xác. Các module [`multimodal.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/multimodal.py) và [`section.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/core/section.py) hỗ trợ luồng xử lý hiện tại; cần kiểm tra chất lượng trích xuất trên các định dạng tài liệu thực tế trước khi kết luận không cần cơ chế bổ sung.

---

## 3. Dự Án Này (`NDQuynh259/ragflow-api`) Nên Dùng Loại Nào?

Không nhất thiết cần 5 pipeline độc lập: có thể dùng một luồng chung với chiến lược/cấu hình phù hợp cho từng section hoặc loại phần tử. Tuy nhiên, khả năng của các module cần được xác nhận theo implementation và dữ liệu đầu vào; tên module không đảm bảo tự động giải quyết mọi trường hợp bố cục.
- **`LayoutNormalizer`**: Có thể hỗ trợ chuẩn hóa quan hệ caption/footnote với phần tử lân cận; cần kiểm chứng trên layout nhiều cột và trường hợp chú thích tách trang.
- **`section.py` (`propagate_sections`)**: Hỗ trợ lan truyền thông tin section; cần xác nhận heading được trích xuất chính xác trước khi dựa vào cây `Chương > Điều > Khoản`.
- **`TableChunker`**: Hỗ trợ chia bảng lớn và giữ header theo thiết kế; cần kiểm tra bảng nhiều tầng header, ô gộp, đơn vị, chú thích và bảng kéo dài qua trang.
- **`ImageChunker`**: Có thể tạo mô tả văn bản cho hình qua Vision VLM; chỉ nên gọi cho hình cần diễn giải, có kiểm soát chi phí và giữ liên kết tới ảnh nguồn.

### Khuyến Nghị Kiến Trúc: Pipeline Hợp Nhất, Chiến Lược Có Điều Kiện
Dùng pipeline chung làm nền tảng, nhưng tránh phân loại toàn bộ tài liệu thành đúng một preset cứng. Một tài liệu có thể chứa nhiều dạng section; nên ưu tiên metadata/layout và cấu trúc từng phần, sau đó áp dụng chunking phù hợp cho section hoặc phần tử. Preset dưới đây là điểm khởi đầu, không thay thế kiểm tra chất lượng:

```
Tài liệu đầu vào
  └─► Trích xuất cấu trúc + metadata (heading, bảng, ảnh, caption, trang, reading order)
        └─► Chọn chiến lược theo section/phần tử, có thể kết hợp:
              ├─ Legal / Policy: ranh giới section + breadcrumb + chia tiếp có kiểm soát
              ├─ Business / Progress / Guide: giữ bảng/hình và ngữ cảnh liên quan khi xác định được
              └─ General / Internal: ranh giới đề mục/đoạn + semantic topic shift
                    └─► Đánh giá retrieval và điều chỉnh cấu hình
```

Nếu cần dùng preset cấp tài liệu, xem đó là gợi ý mặc định; cho phép ngoại lệ theo nội dung thực tế của từng section.

---

## 4. Cấu Hình Tham Số Khởi Đầu Và Cách Chọn

Các kích thước dưới đây tính bằng ký tự chỉ để tạo cấu hình thử nghiệm. Chúng **không tương đương giới hạn token** và không thể coi là tối ưu chung: kết quả phụ thuộc tokenizer, embedding model, độ dài ngữ cảnh, loại dữ liệu và câu hỏi truy vấn. Khi implementation cấu hình theo token, hãy chuyển đổi/đo bằng tokenizer thực tế.

### Nhóm A: "Legal / Policy" (Điều khoản dịch vụ, Quy chế)
* **Ưu tiên:** chunk theo `section_path` và giữ breadcrumb đầy đủ. Không dùng ngưỡng semantic để thay thế ranh giới Điều/Khoản.
* **Khi section vượt giới hạn:** chia tại ranh giới Khoản/Điểm nếu có; giữ breadcrumb và tham chiếu định nghĩa, ngoại lệ hoặc điều khoản liên quan. Chỉ tách bên trong một đơn vị cấu trúc khi cần thiết, và giữ thông tin cho biết đây là phần tiếp nối.
* **Tham số thử nghiệm:** có thể bắt đầu quanh **1500–2000 ký tự**, nhưng phải kiểm tra phân bố độ dài Điều/Khoản và giới hạn model; không đảm bảo một đơn vị pháp lý luôn vừa chunk.
* **`threshold_percentile`:** không gán **95.0** như một biện pháp bảo đảm toàn vẹn pháp lý. Nếu dùng semantic split, đánh giá trên tập dữ liệu riêng và chỉ áp dụng bên trong section.
* **Vision:** không gọi VLM nếu tài liệu không có hình cần hiểu; bật theo sự hiện diện và nhu cầu của phần tử, không chỉ theo nhãn tài liệu.

### Nhóm B: "Business, Progress & Guides"
* **Chiến lược:** multimodal/structure-aware chunking; giữ bảng, caption, ảnh nguồn và văn bản liên quan khi mối liên hệ có đủ tín hiệu.
* **Tham số thử nghiệm:** có thể bắt đầu quanh **1200–1500 ký tự**, sau đó điều chỉnh theo token và kết quả retrieval.
* **Bảng:** giữ header, đơn vị, caption/footnote và nguồn/trang. Với bảng nhiều tầng header, ô gộp hoặc kéo dài qua trang, kiểm tra cấu trúc sau trích xuất; việc lặp header đơn giản có thể không bảo toàn hết ngữ nghĩa.
* **Vision:** chỉ gọi khi có biểu đồ/screenshot cần diễn giải và lợi ích dự kiến xứng đáng với chi phí/độ trễ. Lưu text proxy cùng liên kết đến ảnh nguồn và provenance; không xử lý mặc định mọi ảnh.
* **Reading order:** dùng như tín hiệu, kết hợp heading, caption, nhãn hình và tham chiếu trong văn bản. Khi độ tin cậy thấp, không ghép cưỡng ép; giữ phần tử riêng với metadata liên kết có sẵn.

### Nhóm C: "General Internal" (Wiki, Thông báo, Chính sách)
* **Chiến lược:** kết hợp ranh giới heading/đoạn với hybrid semantic; semantic topic shift là tín hiệu, không thay thế cấu trúc rõ ràng.
* **Tham số thử nghiệm:** có thể bắt đầu quanh **1000–1200 ký tự**; thử một vài cấu hình quanh giá trị này thay vì coi đó là mặc định tối ưu.
* **`threshold_percentile`:** **80.0** chỉ là giá trị ứng viên để đánh giá, không đảm bảo phát hiện topic shift chính xác trên mọi miền tài liệu.

### Đánh giá và tinh chỉnh
Tạo tập câu hỏi đại diện cho cả năm nhóm, kèm tài liệu/đoạn bằng chứng mong đợi. So sánh các cấu hình bằng các chỉ số retrieval phù hợp (ví dụ Recall@k/MRR), kiểm tra thủ công các trường hợp bảng, ngoại lệ pháp lý và liên kết hình-bước; đồng thời theo dõi độ trễ, chi phí VLM và kích thước chunk. Chốt cấu hình theo kết quả đo, không theo nhãn loại tài liệu đơn thuần.

---

> [!TIP]
> **Tóm lại:** Pipeline hợp nhất với chiến lược theo cấu trúc section/phần tử là hướng khởi đầu hợp lý; reading order, phân loại tài liệu, kích thước chunk và ngưỡng semantic đều cần được xem là heuristic/cấu hình thử nghiệm. Với văn bản pháp lý, ưu tiên ranh giới cấu trúc, breadcrumb và chia tiếp có kiểm soát — chỉ tăng `chunk_size` không đủ để đảm bảo bảo toàn nghĩa. Đánh giá bằng tập truy vấn đại diện trước khi chọn cấu hình vận hành.

> **Ghi chú phạm vi:** Tài liệu này mô tả khuyến nghị thiết kế; không khẳng định tất cả cơ chế được nêu đã được triển khai hoặc kiểm chứng đầy đủ trong code hiện tại.
