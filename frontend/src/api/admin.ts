import type {
  DataQualityReport,
  PipelineStatus,
  RetrievalBenchmark,
  SystemOverview,
} from "../types/admin";
import { request } from "./http";

/**
 * Các endpoint admin CHƯA tồn tại ở backend.
 *
 * V3 §11 chỉ định nghĩa backend/app/api/{chat,search,procedures}.py, nên phần
 * monitoring cần bổ sung router riêng trước khi các hàm này chạy được.
 *
 * Tiền tố là "/api/admin" chứ không phải "/admin": "/admin" đã là route giao diện
 * phía frontend, dùng chung sẽ khiến proxy dev nuốt luôn trang admin.
 */
export function getOverview(): Promise<SystemOverview> {
  return request<SystemOverview>("/api/admin/overview");
}

export function getDataQuality(): Promise<DataQualityReport> {
  return request<DataQualityReport>("/api/admin/data-quality");
}

export function getRetrievalBenchmark(): Promise<RetrievalBenchmark> {
  return request<RetrievalBenchmark>("/api/admin/retrieval");
}

export function getPipelineStatus(): Promise<PipelineStatus> {
  return request<PipelineStatus>("/api/admin/pipeline");
}
