import type { ScopeRequest } from "../types/orchestrator";
import type { TodayStorage } from "../types/today";
import type {
  FeedbackDraft,
  RecordKind,
  RecordOperation,
  ReflectionDraft,
  TrialClient,
  TrialDeletePreview,
  TrialReceipt,
  WeeklySnapshot,
} from "../types/trial";
import { readHttpStatus } from "./http-status.ts";

interface Locator {
  kind: RecordOperation;
  request_key: string;
}
export interface TrialState {
  identity: string | null;
  busy: boolean;
  error: string;
  conflict: boolean;
  pending: Locator | null;
  receipt: TrialReceipt | null;
  weekly: WeeklySnapshot | null;
  deletion: TrialDeletePreview | null;
}
const prefix = "filemate-trial-pending-v1:";
export function trialSessionStorage(): TodayStorage {
  return {
    getItem: key => window.sessionStorage.getItem(key),
    setItem: (key, value) => window.sessionStorage.setItem(key, value),
    removeItem: key => window.sessionStorage.removeItem(key),
  };
}
export function trialEpoch(): string {
  try { return window.localStorage.getItem('filemate-today-epoch-v1') ?? ''; }
  catch { return ''; }
}
const validKey = (value: unknown): value is string =>
  typeof value === "string" && /^[A-Za-z0-9_-]{16,80}$/.test(value);

export function createTrialRecordState(
  client: TrialClient,
  storage: TodayStorage,
  options: { epoch: () => string; wrap?: (state: TrialState) => TrialState },
) {
  const fresh = (): TrialState => ({
    identity: null,
    busy: false,
    error: "",
    conflict: false,
    pending: null,
    receipt: null,
    weekly: null,
    deletion: null,
  });
  const state = options.wrap?.(fresh()) ?? fresh();
  let generation = 0,
    boundEpoch = options.epoch(),
    storageReady = true;
  const storageKey = () => prefix + encodeURIComponent(state.identity ?? "");
  const ticket = () => ({
    generation,
    identity: state.identity,
    epoch: options.epoch(),
  });
  function valid(value: ReturnType<typeof ticket>) {
    return (
      value.generation === generation &&
      value.identity === state.identity &&
      value.epoch === options.epoch()
    );
  }
  function bind(identity: string | null) {
    generation++;
    boundEpoch = options.epoch();
    Object.assign(state, fresh(), { identity });
    storageReady = true;
    if (!identity) return;
    try {
      const raw = storage.getItem(storageKey());
      if (!raw) return;
      const value = JSON.parse(raw);
      if (
        !["reflection", "feedback", "delete"].includes(value.kind) ||
        !validKey(value.request_key) ||
        Object.keys(value).length !== 2
      )
        throw new Error("invalid locator");
      state.pending = value;
    } catch {
      storageReady = false;
      state.error = "无法读取已保存请求编号，请恢复浏览器会话存储后重新打开。";
    }
  }
  function invalidate() {
    try {
      if (state.identity) storage.removeItem(storageKey());
    } catch {
      /* Server ownership remains authoritative. */
    }
    bind(null);
  }
  function release() {
    try {
      storage.removeItem(storageKey());
      state.pending = null;
    } catch {
      state.error = "结果已找到，但本机请求编号尚未清理，请再次核验。";
    }
  }
  function accept(receipt: TrialReceipt) {
    if (
      !receipt ||
      !receipt.record_id ||
      !["saved", "deleted"].includes(receipt.status) ||
      receipt.kind !== state.pending?.kind
    )
      throw new Error("invalid receipt");
    state.receipt = receipt;
    state.error = "";
    release();
  }
  function message(error: unknown) {
    const status = readHttpStatus(error);
    if ([400, 401, 403, 409, 410, 422, 429].includes(status ?? 0)) {
      release();
      state.conflict = status === 409;
      state.error =
        status === 409
          ? "记录或依据已经变化，请重新读取后核对。输入仍在本页。"
          : status === 429
            ? "今天的反馈数量已达上限，可以查看已保存记录。"
            : "请求未被接受，请核对输入或重新登录。";
    } else state.error = "结果尚待核验，原请求编号已保留。请查询保存结果。";
  }
  async function perform(
    kind: RecordOperation,
    submit: (key: string) => Promise<TrialReceipt>,
  ) {
    if (state.busy || state.pending || !state.identity || !storageReady) return;
    if (boundEpoch !== options.epoch()) {
      invalidate();
      return;
    }
    const locator = { kind, request_key: globalThis.crypto.randomUUID() };
    try {
      const existing = storage.getItem(storageKey());
      if (existing) {
        const value = JSON.parse(existing);
        if (
          !["reflection", "feedback", "delete"].includes(value.kind) ||
          !validKey(value.request_key)
        )
          throw new Error("invalid locator");
        state.pending = value;
        state.error = "已有请求尚待核验，请先查询原请求结果。";
        return;
      }
      const value = JSON.stringify(locator);
      storage.setItem(storageKey(), value);
      if (storage.getItem(storageKey()) !== value)
        throw new Error("locator not stored");
    } catch {
      state.error = "无法保存请求编号，请启用浏览器会话存储后重试。";
      return;
    }
    state.pending = locator;
    state.busy = true;
    state.conflict = false;
    state.receipt = null;
    state.error = "";
    const current = ticket();
    try {
      const result = await submit(locator.request_key);
      if (valid(current)) accept(result);
    } catch (error) {
      if (valid(current)) message(error);
    } finally {
      if (valid(current)) state.busy = false;
      else if (
        current.generation === generation &&
        current.identity === state.identity
      )
        invalidate();
    }
  }
  async function save(kind: RecordKind, body: ReflectionDraft | FeedbackDraft) {
    const payload = JSON.parse(JSON.stringify(body));
    return perform(kind, (key) =>
      kind === "reflection"
        ? client.saveReflection({
            ...payload,
            request_key: key,
            confirmed: true,
          })
        : client.saveFeedback({
            ...payload,
            request_key: key,
            confirmed: true,
          }),
    );
  }
  async function recover() {
    if (!state.pending || state.busy) return;
    const current = ticket(),
      key = state.pending.request_key;
    state.busy = true;
    try {
      const result = await client.findRequest(key);
      if (valid(current)) accept(result);
    } catch {
      if (valid(current))
        state.error = "还未找到权威回执，请稍后再查询。原请求编号继续保留。";
    } finally {
      if (valid(current)) state.busy = false;
    }
  }
  async function readWeekly(scope: ScopeRequest) {
    const current = ticket();
    state.busy = true;
    state.error = "";
    try {
      const result = await client.readWeekly(scope);
      if (valid(current)) state.weekly = result;
    } catch {
      if (valid(current))
        state.error = "本周安排暂时无法读取，请保留反思内容并重试。";
    } finally {
      if (valid(current)) state.busy = false;
    }
  }
  async function previewDelete(id: string) {
    if (state.busy || state.pending) return;
    const current = ticket();
    state.busy = true;
    try {
      const result = await client.previewDelete(id);
      if (valid(current)) state.deletion = { ...result, record_id: id };
    } catch {
      if (valid(current)) state.error = "删除预览未能读取，请稍后重新核对。";
    } finally {
      if (valid(current)) state.busy = false;
    }
  }
  async function confirmDelete() {
    const preview = state.deletion;
    if (!preview) return;
    await perform("delete", (key) =>
      client.confirmDelete(preview.record_id, {
        request_key: key,
        confirmed: true,
        confirmation_token: preview.confirmation_token,
      }),
    );
    if (state.receipt?.deleted) state.deletion = null;
  }
  return {
    state,
    bind,
    invalidate,
    save,
    recover,
    readWeekly,
    previewDelete,
    confirmDelete,
  };
}
