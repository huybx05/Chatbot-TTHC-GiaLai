import type { ProcedureDocument } from "../data/chatTypes";
import { request } from "./http";

export interface ProcedureDocumentList {
  items: ProcedureDocument[];
}

/** GET /api/v1/procedures/{code}/documents */
export function getProcedureDocuments(
  procedureCode: string,
): Promise<ProcedureDocumentList> {
  return request<ProcedureDocumentList>(
    `/api/v1/procedures/${encodeURIComponent(procedureCode)}/documents`,
  );
}