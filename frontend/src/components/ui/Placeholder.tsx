/** Khung tạm cho các trang chưa triển khai UI. */
export default function Placeholder({ title, note }: { title: string; note?: string }) {
  return (
    <section className="placeholder">
      <h2>{title}</h2>
      {note ? <p className="placeholder__note">{note}</p> : null}
    </section>
  );
}
