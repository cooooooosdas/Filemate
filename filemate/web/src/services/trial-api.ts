import { reviewHTTP as api } from "./api";
import type { ApiResponse } from "../types";
import type { ScopeRequest } from "../types/orchestrator";
import type {
  FeedbackDraft,
  RecordKind,
  ReflectionDraft,
  TrialCapabilities,
  TrialConfirmation,
  TrialDeletePreview,
  TrialDetail,
  TrialPage,
  TrialReceipt,
  WeeklySnapshot,
} from "../types/trial";

const root = "/api/trial";
function result<T>(response: ApiResponse<T>): T {
  if (response.success && response.data != null) return response.data;
  throw new Error("操作尚未完成，请保留输入并重新核对");
}
const get = async <T>(path: string): Promise<T> =>
  result(
    await api.get<unknown, ApiResponse<T>>(root + path, { timeout: 15000 }),
  );
const post = async <T>(path: string, body: unknown): Promise<T> =>
  result(
    await api.post<unknown, ApiResponse<T>>(root + path, body, {
      timeout: 30000,
    }),
  );
export const capabilities = (): Promise<TrialCapabilities> =>
  get("/capabilities");
export const readWeekly = (scope: ScopeRequest): Promise<WeeklySnapshot> =>
  post("/weekly/context", scope);
export const saveReflection = (
  body: ReflectionDraft & TrialConfirmation,
): Promise<TrialReceipt> => post("/reflections", body);
export const saveFeedback = (
  body: FeedbackDraft & TrialConfirmation,
): Promise<TrialReceipt> => post("/feedback", body);
export const findRequest = (key: string): Promise<TrialReceipt> =>
  get("/requests/" + encodeURIComponent(key));
export const listRecords = (
  kind?: RecordKind,
  offset = 0,
): Promise<TrialPage> =>
  get(
    "/records?" +
      new URLSearchParams({
        ...(kind ? { kind } : {}),
        limit: "20",
        offset: String(offset),
      }),
  );
export const detail = (id: string): Promise<TrialDetail> =>
  get("/records/" + encodeURIComponent(id));
export const previewDelete = (id: string): Promise<TrialDeletePreview> =>
  post("/records/" + encodeURIComponent(id) + "/delete-preview", {});
export const confirmDelete = (
  id: string,
  body: TrialConfirmation & { confirmation_token: string },
): Promise<TrialReceipt> =>
  post("/records/" + encodeURIComponent(id) + "/delete-confirm", body);
