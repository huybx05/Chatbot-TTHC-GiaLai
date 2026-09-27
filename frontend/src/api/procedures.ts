import type {
  ProcedureDetail,
  ProcedureSearchResult,
} from "../types/procedure";
import { request } from "./http";

/** GET /search — tra cứu, dùng cho debug retrieval. */
export function searchProcedures(query: string): Promise<ProcedureSearchResult[]> {
  return request<ProcedureSearchResult[]>(`/search?q=${encodeURIComponent(query)}`);
}

/** GET /procedures/{code} — chi tiết một thủ tục. */
export function getProcedure(procedureCode: string): Promise<ProcedureDetail> {
  return request<ProcedureDetail>(`/procedures/${encodeURIComponent(procedureCode)}`);
}
