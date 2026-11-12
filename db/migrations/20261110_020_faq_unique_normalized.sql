-- Chuẩn hóa khóa duy nhất của FAQ.
--
-- Index cũ `(procedure_code, lower(question))` để PostgreSQL coi hai NULL là
-- khác nhau, nên hai FAQ chung cùng câu hỏi vẫn có thể cùng tồn tại. Biểu thức
-- dưới đây coi procedure_code rỗng là một giá trị và chuẩn hóa khoảng trắng ở
-- câu hỏi, khớp với validation trong `backend/app/api/faq_admin.py`.

DROP INDEX IF EXISTS uq_faq_proc_question;

CREATE UNIQUE INDEX IF NOT EXISTS uq_faq_proc_question_norm
    ON faq (
        COALESCE(procedure_code, ''),
        lower(regexp_replace(btrim(question), '\s+', ' ', 'g'))
    );
