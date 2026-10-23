import { type FormEvent, useState } from "react";

import {
  askAdminWorkflow,
  testAdminRetrieval,
  type RetrievalCandidate,
  type RetrievalMode,
  type RetrievalTestResponse,
  type WorkflowAskResponse,
  type WorkflowEvidence,
} from "../../api/admin";
import { ApiError } from "../../api/http";
import { KetQuaHaiBen, NguCanhBangChung, type MucNguCanh, type NguonTraLoi } from "./AnswerSplit.tsx";
import { Badge, Card, Icon, PageHeader } from "./shared.tsx";

/**
 * Nhãn tiếng Việt cho nhánh và kết cục của **luồng**.
 *
 * Giao diện không hiện mã kỹ thuật (`fact_lookup`, `empty`) cho người đọc báo cáo; nhưng khi
 * mã lạ xuất hiện thì hiện nguyên mã — thà lộ mã lạ còn hơn hiện một nhãn sai.
 */
const NHAN_NHANH: Record<string, string> = {
  fact_lookup: "PostgreSQL",
  graph: "Neo4j",
  hybrid: "Hybrid",
  faq: "FAQ",
  "": "Không có nguồn truy xuất",
};

const NHAN_KET_CUC: Record<string, string> = {
  answered: "Có evidence",
  clarify: "Cần hỏi lại",
  need_identity: "Cần biết thủ tục",
  abstained: "Không trả lời được",
  error: "Lỗi",
};

/**
 * Trang kiểm thử truy xuất.
 *
 * ## Trước đây trang này là MOCK
 *
 * Toàn bộ candidate, điểm số và `elapsed_ms` do `buildMockResult()` tự sinh. Nhãn
 * "Dữ liệu mẫu" chỉ là chữ nhỏ — rất dễ chụp màn hình đưa vào báo cáo mà tưởng là
 * kết quả thật.
 *
 * ## Bây giờ
 *
 * Gọi `POST /api/admin/retrieval/test`. Chỉ chế độ `faq` đã triển khai
 * (Giai đoạn 10); các chế độ khác trả HTTP 503 kèm thông báo rõ, **không** trả số
 * liệu giả.
 *
 * ## Vì sao hiện top-K chứ không phải top-1
 *
 * Khi tune ngưỡng cosine, cần biết câu hỏi trượt vì **sát ngưỡng** (0,74) hay **xa**
 * (0,50). Chỉ nhìn top-1 thì không phân biệt được. Vì vậy mỗi candidate có cờ
 * `passed` riêng, tô xanh/đỏ theo ngưỡng.
 */

/**
 * Chế độ của trang kiểm thử.
 *
 * Sáu chế độ sau là **từng động cơ truy xuất chạy lẻ** — người kiểm thử chọn tay để xem một
 * động cơ trả gì. `workflow` là **luồng chính**: hệ thống tự chọn nhánh, người dùng không
 * chọn. Nó đứng đầu danh sách vì đó là thứ người dân thật sự đi qua.
 */
type PlaygroundMode = RetrievalMode | "workflow";

const MODES: Array<{
  value: PlaygroundMode;
  label: string;
  note: string;
  icon: string;
  ready: boolean;
}> = [
  {
    value: "workflow",
    label: "Luồng chính",
    note: "tự chọn nhánh",
    icon: "route",
    ready: true,
  },
  { value: "faq", label: "FAQ", note: "Qdrant + ngưỡng", icon: "quiz", ready: true },
  { value: "keyword", label: "Keyword", note: "BM25", icon: "search", ready: true },
  { value: "vector", label: "Vector", note: "Qdrant cosine", icon: "data_object", ready: true },
  { value: "hybrid", label: "Hybrid", note: "RRF + rerank", icon: "join", ready: true },
  {
    value: "fact_lookup",
    label: "Fact lookup",
    note: "PostgreSQL · metadata",
    icon: "database",
    ready: true,
  },
  { value: "graph", label: "Graph", note: "Neo4j · quan hệ", icon: "hub", ready: true },
];

/**
 * Nhãn nguồn cho khung câu trả lời.
 *
 * Ưu tiên **nguồn đã trích**: đó mới là căn cứ thật của câu trả lời. Chưa sinh được câu trả lời
 * thì lùi về bằng chứng đã tìm, để khung bên trái vẫn nói được "sẽ dùng gì".
 */
function nguonTrichDan(wf: WorkflowAskResponse): NguonTraLoi[] {
  const daTrich = (wf.citations ?? [])
    .filter((trich) => trich.procedure_code || trich.document_code)
    .map((trich) => ({
      nhan: trich.procedure_code || trich.document_code,
      url: trich.detail_url || undefined,
    }));
  if (daTrich.length) return daTrich;

  return (wf.evidence ?? []).slice(0, 6).map((muc) => ({
    nhan: muc.procedure_code || muc.title || muc.kind,
    url: muc.detail_url || undefined,
  }));
}

/** Nhãn nguồn cho khung câu trả lời ở sáu chế độ truy xuất. */
function nguonTuUngVien(result: RetrievalTestResponse): NguonTraLoi[] {
  const daTrich = (result.citations ?? [])
    .filter((trich) => trich.procedure_code || trich.document_code)
    .map((trich) => ({
      nhan: trich.procedure_code || trich.document_code,
      url: trich.detail_url || undefined,
    }));
  if (daTrich.length) return daTrich;

  const daCo = new Set<string>();
  const ra: NguonTraLoi[] = [];
  for (const ung_vien of result.candidates ?? []) {
    const ma = ung_vien.procedure_code;
    if (!ma || daCo.has(ma)) continue;
    daCo.add(ma);
    ra.push({ nhan: ma, url: ung_vien.detail_url || undefined });
    if (ra.length === 6) break;
  }
  return ra;
}

/** Đổi bằng chứng của luồng sang kiểu hiển thị ngữ cảnh. */
function mucNguCanh(danhSach: WorkflowEvidence[] | undefined, toiDa = 50): MucNguCanh[] {
  return (danhSach ?? []).slice(0, toiDa).map((muc) => ({
    kind: muc.kind,
    title: muc.title || muc.section_type || "(không tiêu đề)",
    content: muc.content ?? "",
    procedureCode: muc.procedure_code || undefined,
    section: muc.section_type || undefined,
    score: typeof muc.score === "number" && muc.score > 0 ? muc.score : undefined,
    provenance: muc.provenance || undefined,
    partTitle: muc.part_title || undefined,
    keywordRank: muc.keyword_rank ?? null,
    vectorRank: muc.vector_rank ?? null,
  }));
}

/**
 * Tên **nguồn dữ liệu** ứng với từng chế độ — khác tên chế độ.
 *
 * Ô chọn chế độ ghi *"Fact lookup"* (cách chạy); nhưng trong thẻ ngữ cảnh, thứ người đọc cần
 * biết là **dữ liệu này lấy từ đâu** — `PostgreSQL`, `Neo4j` — để đồng nhất với nhãn nhánh của
 * Luồng chính. Hai câu trả lời khác nhau cho hai câu hỏi khác nhau, nên hai bảng nhãn riêng.
 */
const NGUON_CUA_MODE: Record<PlaygroundMode, string> = {
  workflow: "Luồng chính",
  keyword: "Keyword",
  vector: "Vector",
  faq: "FAQ",
  hybrid: "Hybrid",
  fact_lookup: "PostgreSQL",
  graph: "Neo4j",
};
/** Nhãn tiếng Việt cho `intent` — để đọc được ngay loại thông tin. */
const INTENT_LABELS: Record<string, string> = {
  fee: "Phí, lệ phí",
  processing_time: "Thời hạn",
  required_documents: "Hồ sơ, giấy tờ",
  process_steps: "Trình tự, các bước",
  submit_method: "Hình thức nộp",
  agency: "Cơ quan, thẩm quyền",
  target_audience: "Đối tượng thực hiện",
  result: "Kết quả xử lý",
  condition: "Điều kiện",
  general: "Thông tin chung",
  // Intent của nhánh graph — để badge hiện đúng loại câu hỏi đã được nhận diện.
  AGENCY: "Cơ quan",
  CLASSIFY: "Phân loại",
  RESULT: "Kết quả nhận được",
  AUDIENCE: "Đối tượng thực hiện",
  LEGAL_BASIS_OF_PROCEDURE: "Căn cứ pháp lý",
  PROCEDURES_BY_DOCUMENT: "Thủ tục theo văn bản",
  SHARED_LEGAL_BASIS: "Cùng căn cứ pháp lý",
  TOP_DOCUMENTS: "Văn bản nhiều thủ tục nhất",
  SUBGRAPH: "Toàn cảnh quan hệ",
  DOCUMENT_CANDIDATES: "Văn bản khớp",
  METADATA: "Metadata",
};

/**
 * Nhãn tiếng Việt cho `section_type` của chunk.
 *
 * Dùng ở mode `keyword`/`vector`/`hybrid`: chunk **không có** `intent` như FAQ, nên
 * badge loại thông tin lấy từ `section_type`. Khoá gồm hai dạng giá trị có thật trong
 * dữ liệu: `FEE`/`REQUIRED_DOCUMENTS` (chunk, từ `procedure_sections.section_type`) và
 * `phi`/`thanh_phan_ho_so` (FAQ, từ tên trường JSON gốc).
 */
const SECTION_LABELS: Record<string, string> = {
  GENERAL_INFO: "Thông tin chung",
  STEPS: "Trình tự thực hiện",
  SUBMISSION_METHOD: "Cách thức thực hiện",
  REQUIRED_DOCUMENTS: "Hồ sơ, giấy tờ",
  PROCESSING_TIME: "Thời hạn giải quyết",
  FEE: "Phí, lệ phí",
  RESULT: "Kết quả xử lý",
  LEGAL_BASIS: "Căn cứ pháp lý",
  REQUIREMENTS: "Yêu cầu, điều kiện",
  thong_tin_chung: "Thông tin chung",
  trinh_tu_thuc_hien: "Trình tự thực hiện",
  cach_thuc_thuc_hien: "Cách thức thực hiện",
  thanh_phan_ho_so: "Hồ sơ, giấy tờ",
  thoi_han: "Thời hạn giải quyết",
  phi: "Phí, lệ phí",
  ket_qua_xu_ly: "Kết quả xử lý",
  can_cu_phap_ly: "Căn cứ pháp lý",
  yeu_cau_dieu_kien: "Yêu cầu, điều kiện",
  // Nhãn cho nhánh graph và fact lookup (không phải chunk, không phải FAQ).
  GRAPH: "Đồ thị tri thức",
  METADATA: "Metadata",
};

/** Đổi candidate của một chế độ truy xuất sang kiểu hiển thị ngữ cảnh. */
function mucTuUngVien(
  danhSach: RetrievalCandidate[] | undefined,
  hienThuHang = false,
): MucNguCanh[] {
  return (danhSach ?? []).map((candidate) => ({
    kind: "chunk",
    // Loại thông tin đọc được: FAQ có `intent`, chunk có `section_type` — tra cả hai.
    partTitle:
      INTENT_LABELS[candidate.intent] ??
      SECTION_LABELS[candidate.intent] ??
      SECTION_LABELS[candidate.section_type] ??
      candidate.section_type ??
      undefined,
    title: candidate.title || candidate.section_type || "(không tiêu đề)",
    content: candidate.content ?? "",
    procedureCode: candidate.procedure_code || undefined,
    score: typeof candidate.score === "number" ? candidate.score : undefined,
    // Chỉ nhánh lai mới có **hai** thứ hạng để so; nhánh đơn thì con số đó không nói thêm gì.
    keywordRank: hienThuHang ? (candidate.keyword_rank ?? null) : null,
    vectorRank: hienThuHang ? (candidate.vector_rank ?? null) : null,
  }));
}

export default function RagPlaygroundPage() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<PlaygroundMode>("workflow");
  const [topK, setTopK] = useState(5);
  const [generateAnswer, setGenerateAnswer] = useState(false);
  const [result, setResult] = useState<RetrievalTestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  //: Kết quả **chạy trọn luồng** (luồng tự chọn nhánh). Tách khỏi `result` vì hai thứ trả
  //: lời hai câu hỏi khác nhau: `result` = "động cơ này trả gì", còn đây = "hệ thống chọn
  //: nhánh nào và vì sao".
  const [wfResult, setWfResult] = useState<WorkflowAskResponse | null>(null);


  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) {
      setError("Hãy nhập câu hỏi cần kiểm thử.");
      return;
    }

    setLoading(true);
    setError("");

    // "Luồng chính" không phải một động cơ truy xuất: nó gọi lối vào của cả luồng, và
    // **không** nhận top_k / rerank / sinh câu trả lời. Hai đường gọi tách nhau ngay ở đây
    // để không ai truyền tham số của động cơ sang luồng.
    if (mode === "workflow") {
      try {
        setResult(null);
        setWfResult(await askAdminWorkflow(question.trim()));
      } catch (caught) {
        setWfResult(null);
        setError(caught instanceof ApiError ? caught.message : "Đã xảy ra lỗi không xác định.");
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const response = await testAdminRetrieval({
        question: question.trim(),
        mode,
        top_k: topK,
        generate_answer: generateAnswer,
        // Cổng từ chối không còn nút bật/tắt: luôn bật (backend mặc định `true`),
        // vì đây là cơ chế an toàn duy nhất của nhánh hybrid.
      });
      setWfResult(null);
      setResult(response);
    } catch (caught) {
      setResult(null);
      // `ApiError.message` nay chứa `detail` thật từ backend (503 chưa triển khai,
      // 502 lỗi embedding…), không còn câu chung vô nghĩa.
      setError(caught instanceof ApiError ? caught.message : "Đã xảy ra lỗi không xác định.");
    } finally {
      setLoading(false);
    }
  }

  /**
   * Xoá kết quả khi thay đổi thứ làm kết quả trở nên **không còn đúng**.
   *
   * Kết quả trên màn hình tương ứng với một bộ (câu hỏi, mode, top_k) cụ thể. Nếu giữ
   * lại sau khi đổi mode, người dùng rất dễ đọc nhầm kết quả của Keyword là kết quả của
   * Vector — và đó chính là lúc so sánh hai mode bị sai. Thà trống rồi chạy lại.
   *
   * Không xoá khi đang gõ câu hỏi: xoá giữa lúc gõ sẽ nhấp nháy khó chịu.
   */
  function resetKetQua() {
    setResult(null);
    setError("");
    // Đổi mode là đổi thứ đang được kiểm thử, nên kết quả luồng cũng không còn đúng chỗ.
    setWfResult(null);
  }

  function handleModeChange(next: PlaygroundMode) {
    if (next === mode) return;
    setMode(next);
    resetKetQua();
  }

  return (
    <>
      <PageHeader
        eyebrow="Kiểm thử RAG"
        title="Truy xuất và kiểm tra context"
        description="Chạy một chiến lược truy xuất trên dữ liệu thật, xem điểm từng candidate so với ngưỡng và câu trả lời trước khi sinh."
      />

      <Card>
        <form onSubmit={handleSubmit}>
          <fieldset>
            <legend className="text-sm font-bold">Chọn cách chạy</legend>
            <p className="mt-1 text-xs text-text-secondary">
              <span className="font-semibold text-text-primary">Luồng chính</span> để hệ thống
              tự chọn nhánh · các mục còn lại chạy <span className="font-semibold">một</span>{" "}
              động cơ truy xuất để so sánh từng tín hiệu.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
              {MODES.map((item) => {
                const active = item.value === mode;
                return (
                  <button
                    key={item.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => handleModeChange(item.value)}
                    className={[
                      "flex min-h-16 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                      active
                        ? "border-primary bg-primary-soft text-primary"
                        : "border-border-color bg-card-surface text-text-secondary hover:bg-secondary-surface",
                    ].join(" ")}
                  >
                    <Icon name={item.icon} className="text-[21px]" />
                    <span className="min-w-0">
                      <span className="block text-sm font-bold text-text-primary">
                        {item.label}
                      </span>
                      <span className="block text-xs">
                        {item.ready ? item.note : `${item.note} · chưa có`}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-4 grid gap-3 lg:grid-cols-6">
            <div className={mode === "workflow" ? "lg:col-span-6" : "lg:col-span-4"}>
              <label className="text-sm font-bold" htmlFor="retrieval-question">
                Câu hỏi
              </label>
              <textarea
                id="retrieval-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ví dụ: Phí chuyển nhượng quyền sử dụng đất là bao nhiêu?"
                className="mt-2 min-h-24 w-full resize-y rounded-lg border border-border-color bg-white px-3 py-2.5 text-sm leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
              />
            </div>

            {/* Top K chỉ có nghĩa với một động cơ truy xuất. "Luồng chính" tự quyết định số
                lượng bằng chứng, nên hiện ô này ra là mời người dùng đặt một tham số vô tác dụng. */}
            {mode !== "workflow" ? (
              <div>
                <label className="text-sm font-bold" htmlFor="top-k">
                  Top K
                </label>
                <input
                  id="top-k"
                  type="number"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(event) => {
                    const next = Math.min(20, Math.max(1, Number(event.target.value)));
                    if (next !== topK) {
                      setTopK(next);
                      // Kết quả cũ ứng với Top K cũ; giữ lại là hiển thị sai số lượng.
                      resetKetQua();
                    }
                  }}
                  className="mt-2 h-11 w-full rounded-lg border border-border-color bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                />
              </div>
            ) : null}
          </div>

          <div className="mt-3 flex flex-col gap-3 border-t border-border-color pt-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-col gap-2">
              {mode !== "workflow" && (
                <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-text-secondary">
                  <input
                    type="checkbox"
                    checked={generateAnswer}
                    onChange={(event) => setGenerateAnswer(event.target.checked)}
                    className="size-4 accent-primary"
                  />
                  Sinh câu trả lời từ context
                </label>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={loading}
                className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-primary-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Đang chạy..." : "Chạy kiểm thử"}
              </button>
            </div>
          </div>
        </form>
      </Card>

      {wfResult ? (
        <KetQuaHaiBen
          traLoi={wfResult.answer || null}
          ghiChuTraLoi={
            wfResult.answer_error
              ? `Chưa sinh được câu trả lời: ${wfResult.answer_error}`
              : wfResult.evidence.length
                ? "Bật mô hình sinh câu trả lời để có câu trả lời cho người dân."
                : undefined
          }
          nguon={nguonTrichDan(wfResult)}
          tieuDeNguCanh="Ngữ cảnh cấp cho mô hình"
          huyHieuNguCanh={
            <>
              <Badge tone="info">{NHAN_NHANH[wfResult.branch] ?? wfResult.branch}</Badge>
              <Badge tone={wfResult.outcome === "answered" ? "ok" : "warn"}>
                {NHAN_KET_CUC[wfResult.outcome] ?? wfResult.outcome}
              </Badge>
            </>
          }
          noiDungNguCanh={<NguCanhBangChung items={mucNguCanh(wfResult.evidence)} dayDu />}
        />
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger"
        >
          {error}
        </div>
      ) : null}

      {result ? (
        <KetQuaHaiBen
          traLoi={result.answer || null}
          ghiChuTraLoi={
            result.answer_error
              ? `Chưa sinh được câu trả lời: ${result.answer_error}`
              : result.candidates.length
                ? "Bật ô “Sinh câu trả lời từ context” rồi chạy lại để có câu trả lời."
                : undefined
          }
          nguon={nguonTuUngVien(result)}
          tieuDeNguCanh="Ngữ cảnh cấp cho mô hình"
          huyHieuNguCanh={
            <>
              <Badge tone="info">{NGUON_CUA_MODE[result.mode]}</Badge>
              <Badge
                tone={
                  result.refused
                    ? "bad"
                    : result.threshold != null && !result.passed
                      ? "warn"
                      : "ok"
                }
              >
                {result.refused
                  ? "Đã từ chối"
                  : result.threshold != null
                    ? result.passed
                      ? "Đạt ngưỡng"
                      : "Trượt ngưỡng"
                    : "Chỉ truy xuất"}
              </Badge>
            </>
          }
          noiDungNguCanh={
            <NguCanhBangChung
              items={mucTuUngVien(result.candidates, result.mode === "hybrid")}
              loaiHienThi={NGUON_CUA_MODE[result.mode]}
              dayDu
            />
          }
        />
      ) : null}
    </>
  );
}
