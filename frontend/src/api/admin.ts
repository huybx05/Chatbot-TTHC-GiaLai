import { request } from "./http";

export type AdminProcedure = {
  code: string;
  name: string;
  domain_group: string;
  source_field: string;
  canonical_field: string;
  administrative_levels: string[];
  issuing_agency: string;
  status: string;
  detail_url: string;
  section_count: number;
};

export type AdminProcedureDetail = Record<string, unknown> & {
  procedure_code: string;
  procedure_name: string;
  agencies?: { agency_name: string; role: string; is_inferred: boolean }[];
};

export type AdminSection = {
  section_id: string;
  chunk_id: string;
  section_type: string;
  title: string;
  content: string;
  chunk_order: number;
  detail_url: string;
};

export type AdminQaPair = {
  id: string;
  faq_id?: string;
  question: string;
  answer: string;
  procedure_code: string;
  procedure_name?: string;
  domain_group?: string;
  source_field?: string;
  intent?: string;
  source_section?: string;
  source_text?: string;
  tags?: string[];
  status: string;
  score: number;
  confidence?: number;
  created_at?: string;
  updated_at?: string;
};

export type GraphNode = {
  id: string;
  label: string;
  name: string;
  properties?: Record<string, unknown>;
};

export type GraphEdge = {
  source: string;
  target: string;
  type: string;
};

export type GraphStats = {
  nodes: { label: string; count: number }[];
  relationships: { type: string; count: number }[];
};

export type ServiceStatus = {
  ready: boolean;
  error: string;
  counts?: Record<string, number>;
  index?: string;
  exists?: boolean;
  documents?: number;
  collections?: {
    semantic?: { name: string; exists: boolean; points: number };
    faq?: { name: string; exists: boolean; points: number };
  };
};

export type AdminSystemStatus = {
  services: Record<"api" | "postgresql" | "neo4j" | "elasticsearch" | "qdrant", ServiceStatus>;
};

export function getAdminSystemStatus() {
  return request<AdminSystemStatus>("/api/admin/system/status");
}

export function getAdminProcedures(q = "") {
  return request<{ items: AdminProcedure[] }>(`/api/admin/procedures?q=${encodeURIComponent(q)}`);
}

export function getAdminProcedure(code: string) {
  return request<{ item: AdminProcedureDetail | null }>(`/api/admin/procedures/${code}`);
}

export function getAdminSections(code: string) {
  return request<{ items: AdminSection[] }>(`/api/admin/procedures/${code}/sections`);
}

export function getAdminQa(procedureCode: string) {
  return request<{ items: AdminQaPair[] }>(`/api/admin/qa?procedure_code=${encodeURIComponent(procedureCode)}`);
}

export function approveAdminQa(id: string) {
  return request<{ updated: number }>(`/api/admin/qa/${id}/approve`, { method: "POST" });
}

export function approveAllAdminQa(procedureCode = "") {
  return request<{ updated: number }>(`/api/admin/qa/approve-all?procedure_code=${encodeURIComponent(procedureCode)}`, { method: "POST" });
}

export function getGraphStats() {
  return request<GraphStats>("/api/admin/graph/stats");
}

export function getFullGraph() {
  return request<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/api/admin/graph");
}

export function getProcedureGraph(code: string) {
  return request<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/api/admin/graph/procedures/${code}`);
}
