import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";

import {
  getFullGraph,
  getGraphStats,
  getProcedureGraph,
  type GraphEdge,
  type GraphNode,
  type GraphStats,
} from "../../api/admin";
import { Badge, Card, MetricCard, PageHeader, SectionTitle } from "./shared.tsx";

type ForceNode = GraphNode & { id: string; fx?: number; fy?: number; x?: number; y?: number };
type ForceLink = GraphEdge & { source: string | ForceNode; target: string | ForceNode };

/** Đầu mút của cạnh sau khi mô phỏng: `source`/`target` đã được thay bằng chính object node. */
type LinkEndpoint = ForceNode & { x?: number; y?: number };

function isPositionedNode(value: string | ForceNode): value is LinkEndpoint {
  return typeof value !== "string" && typeof value.x === "number" && typeof value.y === "number";
}

const COLORS: Record<string, string> = {
  ThuTuc: "#00c2d7",
  CoQuan: "#57d9d5",
  VanBanPhapLy: "#e3c437",
  LinhVuc: "#f5d8b7",
  DoiTuong: "#74a9c3",
  KetQua: "#d2908d",
  CapHanhChinh: "#f38ad8",
  TrangThai: "#c9da86",
  DomainGroup: "#8fd3e8",
};

function colorOf(label: string) {
  return COLORS[label] ?? "#d8cec3";
}

function propertyText(node: ForceNode, key: string) {
  const value = node.properties?.[key];
  return value === undefined || value === null ? "" : String(value);
}

function shortLabel(node: ForceNode) {
  const text = node.label === "ThuTuc" ? propertyText(node, "ma") || propertyText(node, "key") || node.name : node.name;
  return text.length > 24 ? `${text.slice(0, 22)}…` : text;
}

function propertyEntries(node: GraphNode) {
  return Object.entries(node.properties ?? {}).filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "");
}

function graphId(value: string | ForceNode) {
  return typeof value === "string" ? value : String(value.id);
}

export default function GraphPage() {
  const graphRef = useRef<ForceGraphMethods<ForceNode, ForceLink> | undefined>(undefined);
  const [code, setCode] = useState("");
  const [mode, setMode] = useState("Toàn bộ graph");
  const [stats, setStats] = useState<GraphStats>({ nodes: [], relationships: [] });
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [graphKey, setGraphKey] = useState(0);

  // Trạng thái hover để đổi con trỏ; đổi state chỉ khi giá trị ĐỔI.
  const [cursorOnNode, setCursorOnNode] = useState(false);

  /**
   * Tìm node gần toạ độ graph nhất, trong bán kính cho phép.
   *
   * VÌ SAO PHẢI TỰ DÒ: `nodePointerAreaPaint` của react-force-graph-2d là prop HỎNG ở bản
   * đang cài. Nó nối vào `shadowGraph.nodeCanvasObject`, nhưng `nodeCanvasObjectMode` của
   * graph chính là hàm trả `"replace"` mà shadow graph không nhận được giá trị đó, nên
   * shadow graph dùng default `"replace"` và BỎ QUA `nodeCanvasObject` → canvas bấm không
   * bao giờ được vẽ → không node nào nhận được chuột (đo thực tế: 0/6 rê, 0/6 bấm).
   *
   * Nên ở đây dò thẳng trên dữ liệu node, không dựa vào canvas bấm của thư viện.
   */
  function hitTest(point: { x: number; y: number }): ForceNode | null {
    const graph = graphRef.current;
    let best: ForceNode | null = null;
    let bestDistance = Infinity;
    for (const node of graphData.nodes) {
      const item = node as ForceNode;
      if (item.x === undefined || item.y === undefined) continue;
      const dx = item.x - point.x;
      const dy = item.y - point.y;
      const distance = Math.hypot(dx, dy);
      // Bán kính tính theo pixel màn hình rồi chia cho mức zoom, để vùng bấm không
      // phình ra khi zoom xa và không teo lại khi zoom gần.
      const zoom = graph && typeof graph.zoom === "function" ? graph.zoom() || 1 : 1;
      const hitRadius = (item.label === "ThuTuc" ? 12 : 8) / zoom;
      if (distance <= hitRadius && distance < bestDistance) {
        best = item;
        bestDistance = distance;
      }
    }
    return best;
  }

  function graphPointFromEvent(event: { clientX: number; clientY: number }, element: HTMLElement) {
    const graph = graphRef.current;
    const rect = element.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    return graph ? graph.screen2GraphCoords(localX, localY) : { x: localX, y: localY };
  }

  function handleCanvasMove(event: React.MouseEvent<HTMLDivElement>) {
    const on = Boolean(hitTest(graphPointFromEvent(event, event.currentTarget)));
    // Chỉ đổi state khi trạng thái hover ĐỔI — set mỗi lần chuột nhích sẽ re-render liên tục.
    setCursorOnNode((current) => (current === on ? current : on));
  }

  function handleCanvasClick(event: React.MouseEvent<HTMLDivElement>) {
    const hit = hitTest(graphPointFromEvent(event, event.currentTarget));
    if (hit) setSelectedId(String(hit.id));
  }

  const graphData = useMemo(
    () => ({
      /**
       * Đỉnh `ThuTuc` phải nằm CUỐI mảng.
       *
       * `force-graph` vẽ đỉnh theo đúng thứ tự mảng, cả trên canvas hiển thị lẫn canvas
       * bấm (`nodePointerAreaPaint` chính là `nodeCanvasObject` của canvas ẩn). Đỉnh vẽ
       * sau đè lên đỉnh vẽ trước, nên đỉnh nằm cuối là đỉnh bấm được.
       *
       * Backend trả `ThuTuc` trước vì nó luôn là `source` của mọi dòng. Không đảo lại thì
       * nút thủ tục — vốn nhiều cạnh nhất nên bị lực kéo vào giữa, chui xuống dưới các
       * nhãn khác — sẽ bị chôn và bấm không tới.
       */
      nodes: [...nodes].sort(
        (a, b) => Number(a.label === "ThuTuc") - Number(b.label === "ThuTuc"),
      ),
      links: edges.map((edge) => ({ ...edge })),
    }),
    [edges, nodes],
  );
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const selected = nodeById.get(selectedId);
  const relatedEdgeTypes = useMemo(
    () => edges.filter((edge) => edge.source === selectedId || edge.target === selectedId).map((edge) => edge.type),
    [edges, selectedId],
  );

  function selectNode(node: ForceNode) {
    setSelectedId(String(node.id));
  }

  /**
   * Danh sách đỉnh thủ tục đang có trên graph, để chọn trực tiếp từ panel.
   *
   * Mục đích: khi trình bày, việc bấm đúng vào một chấm nhỏ có thể trượt. Chọn từ danh sách
   * này cho kết quả chắc chắn và vẫn kích hoạt đúng phần tô sáng edge như bấm trên canvas.
   */
  const procedureNodes = useMemo(
    () =>
      nodes
        .filter((node) => node.label === "ThuTuc")
        .map((node) => ({
          id: node.id,
          code: propertyText(node as ForceNode, "ma") || propertyText(node as ForceNode, "key"),
          name: node.name,
        })),
    [nodes],
  );

  function loadFullGraph() {
    getFullGraph()
      .then((res) => {
        setNodes(res.nodes);
        setEdges(res.edges);
        setSelectedId("");
        setMode("Toàn bộ graph");
        setGraphKey((value) => value + 1);
        setError("");
      })
      .catch(() => setError("Không tải được toàn bộ graph Neo4j."));
  }

  function loadProcedureGraph() {
    if (!code.trim()) {
      loadFullGraph();
      return;
    }

    getProcedureGraph(code.trim())
      .then((res) => {
        setNodes(res.nodes);
        setEdges(res.edges);
        setSelectedId("");
        setMode(`Lọc theo thủ tục ${code.trim()}`);
        setGraphKey((value) => value + 1);
        setError("");
      })
      .catch(() => setError("Không tải được graph của thủ tục."));
  }

  useEffect(() => {
    getGraphStats()
      .then(setStats)
      .catch(() => setError("Không tải được thống kê Neo4j."));
    loadFullGraph();
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Neo4j Graph"
        title="Trực quan hóa CSDL đồ thị của hệ thống"
        description="Mặc định hiển thị toàn bộ graph. Nhập mã thủ tục rồi tìm kiếm nếu chỉ muốn xem một thủ tục cụ thể."
      />

      {error ? (
        <div className="mb-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger">
          {error}
        </div>
      ) : null}

      <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon="hub" label="Graph status" value="Ready" note={mode} tone="ok" />
        <MetricCard icon="account_tree" label="Loại relationship" value={String(stats.relationships.length)} note="Theo dữ liệu hiện có" tone="info" />
        <MetricCard icon="database" label="Loại node" value={String(stats.nodes.length)} note="Nhãn trong graph" tone="info" />
        <MetricCard icon="share" label="Đang hiển thị" value={`${nodes.length}/${edges.length}`} note="node / relationship" tone="info" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <div className="mb-4 grid gap-2 md:grid-cols-[1fr_150px_150px]">
            <input
              className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary"
              placeholder="Nhập mã thủ tục để lọc, ví dụ 1.014100"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <button className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white" type="button" onClick={loadProcedureGraph}>
              Tìm kiếm thủ tục
            </button>
            <button className="rounded-lg border border-border-color bg-secondary-surface px-4 py-2 text-sm font-bold text-text-secondary" type="button" onClick={loadFullGraph}>
              Toàn bộ graph
            </button>
          </div>
          <div
            className="h-[640px] overflow-hidden rounded-xl border border-border-color bg-[#181b1f]"
            style={{ cursor: cursorOnNode ? "pointer" : "default" }}
            onMouseMove={handleCanvasMove}
            onClick={handleCanvasClick}
          >
            <ForceGraph2D
              ref={graphRef}
              key={graphKey}
              graphData={graphData}
              backgroundColor="#181b1f"
              enableNodeDrag
              nodeLabel={(node) => {
                const item = node as ForceNode;
                return `${item.label}: ${shortLabel(item)}\n${item.name}`;
              }}
              nodeColor={(node) => colorOf(String((node as ForceNode).label))}
              nodeRelSize={5}
              nodeVal={(node) => ((node as ForceNode).label === "ThuTuc" ? 3.2 : 2)}
              nodeCanvasObjectMode={() => "replace"}
              nodeCanvasObject={(node, ctx, globalScale) => {
                const item = node as ForceNode & { x?: number; y?: number };
                const x = item.x ?? 0;
                const y = item.y ?? 0;
                const isProcedure = item.label === "ThuTuc";
                const radius = isProcedure ? 7.5 : 5.5;
                const selectedNode = selectedId === String(item.id);

                ctx.beginPath();
                ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
                ctx.fillStyle = colorOf(item.label);
                ctx.fill();
                ctx.lineWidth = selectedNode ? 3 / globalScale : 1 / globalScale;
                ctx.strokeStyle = selectedNode ? "#fffdf9" : "#181b1f";
                ctx.stroke();

                if (selectedNode) {
                  ctx.beginPath();
                  ctx.arc(x, y, radius + 4 / globalScale, 0, 2 * Math.PI, false);
                  ctx.lineWidth = 2 / globalScale;
                  ctx.strokeStyle = "rgba(255, 253, 249, 0.65)";
                  ctx.stroke();
                }

                const label = shortLabel(item);
                const fontSize = isProcedure ? 11 / globalScale : 9 / globalScale;
                ctx.font = `700 ${fontSize}px Inter, Arial, sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "top";

                const textWidth = ctx.measureText(label).width;
                const padding = 3 / globalScale;
                const textY = y + radius + 3 / globalScale;

                ctx.fillStyle = "rgba(24, 27, 31, 0.78)";
                ctx.fillRect(x - textWidth / 2 - padding, textY - padding / 2, textWidth + padding * 2, fontSize + padding * 1.6);
                ctx.fillStyle = "#f8efe4";
                ctx.fillText(label, x, textY);
              }}
              nodePointerAreaPaint={(node, color, ctx) => {
                const item = node as ForceNode & { x?: number; y?: number };
                const x = item.x ?? 0;
                const y = item.y ?? 0;
                const isProcedure = item.label === "ThuTuc";

                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(x, y, (isProcedure ? 7.5 : 5.5) + 4, 0, 2 * Math.PI, false);
                ctx.fill();

                if (isProcedure) {
                  const label = shortLabel(item);
                  ctx.font = "700 11px Inter, Arial, sans-serif";
                  const textWidth = ctx.measureText(label).width;
                  ctx.fillRect(x - textWidth / 2 - 6, y + 6, textWidth + 12, 18);
                }
              }}
              linkColor={(link) => {
                const item = link as ForceLink;
                return selectedId && (graphId(item.source) === selectedId || graphId(item.target) === selectedId) ? "#f2e7d8" : "#8d949e";
              }}
              linkLabel={(link) => String((link as ForceLink).type)}
              /**
               * Vẽ TÊN QUAN HỆ lên chính đường edge.
               *
               * `linkLabel` chỉ là tooltip khi rê chuột — thư viện không vẽ nhãn lên đường.
               * Muốn thấy thường trực thì phải tự vẽ. Chế độ `"after"` để nhãn nằm ĐÈ LÊN
               * đường, không bị đường vẽ sau che mất.
               */
              linkCanvasObjectMode={() => "after"}
              linkCanvasObject={(link, ctx, globalScale) => {
                const item = link as ForceLink;
                // Chỉ hiện nhãn của quan hệ thuộc đỉnh đang chọn khi đã có đỉnh được chọn,
                // để graph dày không rối. Chưa chọn gì thì hiện hết.
                const isNeighbourEdge =
                  Boolean(selectedId) &&
                  (graphId(item.source) === selectedId || graphId(item.target) === selectedId);
                if (selectedId && !isNeighbourEdge) return;

                const source = item.source;
                const target = item.target;
                if (!isPositionedNode(source) || !isPositionedNode(target)) return;
                const sx = source.x as number;
                const sy = source.y as number;
                const tx = target.x as number;
                const ty = target.y as number;

                const label = String(item.type);
                if (!label) return;

                // Đặt nhãn ở giữa đường, xoay theo hướng đường.
                const midX = (sx + tx) / 2;
                const midY = (sy + ty) / 2;
                let angle = Math.atan2(ty - sy, tx - sx);
                // Lật nhãn lại nếu đường dốc ngược, để chữ không bị lộn ngược.
                if (angle > Math.PI / 2) angle -= Math.PI;
                else if (angle < -Math.PI / 2) angle += Math.PI;

                const fontSize = 10 / globalScale;
                ctx.save();
                ctx.translate(midX, midY);
                ctx.rotate(angle);
                ctx.font = `600 ${fontSize}px Inter, Arial, sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";

                const textWidth = ctx.measureText(label).width;
                const padX = 4 / globalScale;
                const textHeight = fontSize * 1.4;
                ctx.fillStyle = isNeighbourEdge ? "rgba(24, 27, 31, 0.92)" : "rgba(24, 27, 31, 0.68)";
                ctx.fillRect(-textWidth / 2 - padX, -textHeight / 2, textWidth + padX * 2, textHeight);
                ctx.fillStyle = isNeighbourEdge ? "#ffd166" : "#c9c2b8";
                ctx.fillText(label, 0, 0);
                ctx.restore();
              }}
              linkWidth={(link) => {
                const item = link as ForceLink;
                return selectedId && (graphId(item.source) === selectedId || graphId(item.target) === selectedId) ? 1.8 : 0.7;
              }}
              linkDirectionalParticles={(link) => ((link as ForceLink).type === "THU_TUC_LIEN_QUAN" ? 2 : 0)}
              linkDirectionalParticleSpeed={0.004}
              onNodeDragEnd={(node) => {
                // Ghim vị trí sau khi kéo (hành vi gốc). Không đổi lựa chọn ở đây nữa vì
                // việc chọn đã do lớp phủ bên ngoài xử lý.
                const item = node as ForceNode;
                item.fx = item.x;
                item.fy = item.y;
              }}
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(COLORS).map(([label, color]) => (
              <span key={label} className="inline-flex items-center gap-2 rounded-full border border-border-color bg-card-surface px-3 py-1 text-xs font-semibold text-text-secondary">
                <span className="size-2.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </span>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <SectionTitle
              title={`Các thủ tục trên đồ thị (${procedureNodes.length})`}
              note="Bấm để chọn — chắc chắn hơn bấm vào chấm trên canvas."
            />
            <div className="max-h-64 space-y-2 overflow-auto">
              {procedureNodes.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectNode({ id: item.id } as ForceNode)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selectedId === item.id
                      ? "border-primary bg-primary-soft"
                      : "border-border-color bg-secondary-surface hover:border-primary"
                  }`}
                >
                  <p className="text-sm font-bold">{item.code || item.name}</p>
                  <p className="mt-1 text-xs leading-5 text-text-secondary">{item.name}</p>
                </button>
              ))}
              {!procedureNodes.length ? (
                <p className="text-sm text-text-secondary">Graph hiện không có đỉnh thủ tục nào.</p>
              ) : null}
            </div>
          </Card>

          <Card>
            <SectionTitle title="Node đang chọn" note="Bấm vào một Node trong graph để xem chi tiết." />
            {selected ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-border-color bg-secondary-surface p-3">
                  <p className="text-xs font-bold uppercase text-text-secondary">{selected.label}</p>
                  <p className="mt-2 text-sm font-bold leading-6">
                    {selected.label === "ThuTuc" ? propertyText(selected as ForceNode, "ma") || propertyText(selected as ForceNode, "key") : selected.name}
                  </p>
                  {selected.label === "ThuTuc" ? <p className="mt-1 text-sm leading-6 text-text-secondary">{selected.name}</p> : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {relatedEdgeTypes.slice(0, 12).map((type, index) => (
                    <Badge key={`${type}-${index}`} tone="info">{type}</Badge>
                  ))}
                </div>
                <div className="max-h-80 space-y-2 overflow-auto rounded-lg border border-border-color bg-card-surface p-3">
                  {propertyEntries(selected).map(([key, value]) => (
                    <div key={key} className="border-b border-border-color pb-2 last:border-b-0 last:pb-0">
                      <p className="text-[11px] font-bold uppercase text-text-secondary">{key}</p>
                      <p className="mt-1 break-words text-sm font-semibold leading-5">{String(value)}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Chưa chọn node.</p>
            )}
          </Card>

          <Card>
            <SectionTitle title="Thống kê node" />
            <div className="space-y-2">
              {stats.nodes.map((item) => (
                <div key={item.label} className="flex items-center justify-between rounded-lg border border-border-color bg-secondary-surface p-3">
                  <span className="text-sm font-bold">{item.label}</span>
                  <span className="text-sm font-semibold text-text-secondary">{item.count}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <SectionTitle title="Relationship chính" note="Đọc trực tiếp từ Neo4j." />
            <div className="space-y-2">
              {stats.relationships.map((item) => (
                <div key={item.type} className="rounded-lg border border-border-color p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-bold">{item.type}</p>
                    <Badge tone="info">{String(item.count)}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
