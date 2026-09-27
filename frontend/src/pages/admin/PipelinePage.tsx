import Placeholder from "../../components/ui/Placeholder.tsx";

/** Trạng thái pipeline: ingest → parse → validate → chunk, để thấy chỗ nào còn kẹt. */
export default function PipelinePage() {
  return (
    <Placeholder
      title="Trạng thái pipeline"
      note="Tiến độ PENDING/DONE/FAILED của từng bước, đọc từ manifest và checkpoint."
    />
  );
}
