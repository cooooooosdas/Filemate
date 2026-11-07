import type { ScopeRequest, TaskView } from "./orchestrator";

export type RecordKind = "reflection" | "feedback";
export type RecordOperation = RecordKind | "delete";
export type FeedbackCategory = "bug" | "suggestion" | "other";
export type FeedbackModule =
  | "home"
  | "today"
  | "goals"
  | "learning"
  | "wrongbook"
  | "graph"
  | "programming"
  | "interview"
  | "career"
  | "privacy"
  | "other";
export interface TrialCapabilities {
  enabled: boolean;
  ui_contract: string;
  limits: { feedback_per_day: number; text_characters: number; page: number };
}
export interface TrialReceipt {
  record_id: string;
  kind: RecordOperation;
  status: "saved" | "deleted";
  created_at: string;
  deleted?: boolean;
  affected?: Record<string, number>;
}
export interface WeeklySummary {
  planned_days: number;
  total_tasks: number;
  completed_tasks: number;
  pending_tasks: number;
  unresolved_tasks: number;
  overdue_tasks: number;
}
export interface WeeklyItem {
  task_id: string;
  status: "completed" | "pending" | "unresolved";
  dates: string[];
  task: TaskView | null;
}
export interface WeeklySnapshot {
  rule_version: string;
  scope: ScopeRequest;
  week_start: string;
  week_end: string;
  study_date: string;
  as_of: string;
  revision: string;
  summary: WeeklySummary;
  items: WeeklyItem[];
  coverage: {
    meaning: string;
    excluded_days: number;
    invalid_days: number;
    omitted_items: number;
    truncated: boolean;
  };
}
export interface ReflectionDraft {
  scope: ScopeRequest;
  expected_revision: string;
  reason: "time" | "difficulty" | "unclear" | "progress" | "other";
  notes: string;
}
export interface FeedbackDraft {
  category: FeedbackCategory;
  module: FeedbackModule;
  description: string;
  steps: string;
  client_version: string;
}
export interface TrialConfirmation {
  request_key: string;
  confirmed: true;
}
export interface TrialSummary {
  record_id: string;
  kind: RecordKind;
  title: string;
  created_at: string;
}
export interface TrialPage {
  items: TrialSummary[];
  total: number;
  limit: number;
  offset: number;
}
export interface TrialDetail extends Omit<TrialSummary, "title"> {
  content: Record<string, unknown>;
}
export interface TrialDeletePreview {
  record_id: string;
  kind: RecordKind;
  confirmation_token: string;
  affected: Record<string, number>;
  expires_in_seconds: number;
}
export interface TrialClient {
  capabilities(): Promise<TrialCapabilities>;
  readWeekly(scope: ScopeRequest): Promise<WeeklySnapshot>;
  saveReflection(
    body: ReflectionDraft & TrialConfirmation,
  ): Promise<TrialReceipt>;
  saveFeedback(body: FeedbackDraft & TrialConfirmation): Promise<TrialReceipt>;
  findRequest(key: string): Promise<TrialReceipt>;
  listRecords(kind?: RecordKind, offset?: number): Promise<TrialPage>;
  detail(id: string): Promise<TrialDetail>;
  previewDelete(id: string): Promise<TrialDeletePreview>;
  confirmDelete(
    id: string,
    body: TrialConfirmation & { confirmation_token: string },
  ): Promise<TrialReceipt>;
}
