/** Section chuẩn của một thủ tục — khớp data contract ở docs/data_schema.md. */
export type SectionType =
  | "GENERAL_INFO"
  | "PROCEDURE_STEPS"
  | "REQUIRED_DOCUMENTS"
  | "SUBMISSION_METHOD"
  | "PROCESSING_TIME"
  | "FEE"
  | "REQUIREMENTS"
  | "RESULT"
  | "LEGAL_BASIS"
  | "OTHER";

export interface ProcedureSection {
  section_type: SectionType;
  section_title: string;
  content: string;
  page_number?: number;
}

export interface ProcedureDetail {
  procedure_code: string;
  procedure_name: string;
  domain_group?: string;
  source_field?: string;
  canonical_field?: string;
  agency?: string;
  administrative_level?: string;
  province?: string | null;
  source_url?: string;
  sections: ProcedureSection[];
}

export interface ProcedureSearchResult {
  chunk_id: string;
  procedure_code: string;
  procedure_name: string;
  section_type: SectionType;
  content: string;
  score: number;
}
