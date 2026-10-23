/** Thanh header phía trên vùng chat. */
export default function ChatHeader({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  return (
    <header className="fixed top-0 left-0 right-0 z-40 flex h-16 items-center border-b border-border-color bg-main-bg/90 px-4 backdrop-blur-md md:left-[260px] md:px-8">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Mở danh mục"
          onClick={onOpenSidebar}
          className="rounded-lg p-2 text-text-secondary hover:bg-sidebar-bg hover:text-text-primary md:hidden"
        >
          <span className="material-symbols-outlined">menu</span>
        </button>
        <div className="flex items-center gap-2">
          <span className="text-[17px] font-semibold text-text-primary">
            Hệ Thống Hỗ Trợ Tra Cứu Thủ Tục Hành Chính Tại Tỉnh Gia Lai
          </span>
        </div>
      </div>
    </header>
  );
}
