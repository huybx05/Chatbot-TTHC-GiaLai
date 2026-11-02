import { request } from "./http";

export function recordPageVisit() {
  return request<{ recorded: boolean }>("/api/v1/visits", { method: "POST" });
}
