/** Trạng thái loading / error / rỗng dùng chung cho cả 2 giao diện. */

export function Loading({ label = "Đang xử lý..." }: { label?: string }) {
  return <p className="state state--loading">{label}</p>;
}

export function Empty({ label }: { label: string }) {
  return <p className="state state--empty">{label}</p>;
}

export function ErrorState({
  label = "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau.",
  onRetry,
}: {
  label?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state state--error">
      <p>{label}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Thử lại
        </button>
      ) : null}
    </div>
  );
}
