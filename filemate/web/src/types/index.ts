// Session 状态
export type SessionStatus =
  | 'pending'
  | 'processing'
  | 'done'
  | 'confirmed'
  | 'skipped'
  | 'expired'
  | 'failed'

// 文件分类
export type Category =
  | '课件'
  | '作业'
  | '竞赛通知'
  | '考试通知'
  | '参考资料'
  | '大创通知'
  | '待确认'

// ProcessingSession
export interface ProcessingSession {
  session_id: string
  source_path: string
  status: SessionStatus
  category: Category | ''
  confidence: number
  suggested_name: string
  entities: Record<string, any>
  milestones: Milestone[]
  error: string
  created_at: string
  updated_at: string
  execution?: ExecutionRecord | null
  can_undo?: boolean
}

export interface ExecutionRecord {
  execution_id: string
  status: 'pending' | 'applied' | 'undone' | 'failed'
  source_path: string
  dest_path: string
  ics_path?: string | null
  error?: string
  created_at?: string
  applied_at?: string | null
  undone_at?: string | null
  can_undo?: boolean
  idempotent?: boolean
}

// 里程碑
export interface Milestone {
  event: string
  date: string
  order: number
}

// 文件元数据
export interface FileMetadata {
  filename: string
  suffix: string
  size_bytes: number
  pages?: number
  slides?: number
}

// API 响应
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
}

// 上传响应
export interface UploadResponse extends ProcessingSession {
  message?: string
}

// 确认请求
export interface ConfirmRequest {
  accepted: boolean
  edits?: Record<string, any>
}

// 确认响应
export interface ConfirmResponse {
  ok: boolean
  session_id: string
  accepted: boolean
  execution?: ExecutionRecord | null
  error?: string
}

export interface UndoResponse {
  ok: boolean
  session_id: string
  execution: ExecutionRecord
}

// 历史记录项
export interface HistoryItem {
  session_id: string
  source_path: string
  status: SessionStatus
  category: string
  suggested_name: string
  created_at: string
  updated_at: string
  execution?: ExecutionRecord | null
  can_undo?: boolean
}

// ─── AI 辅助学习 ──────────────────────────────

export type AILearningMode = 'explore' | 'reinforce'

export interface AICitation {
  source_id: string
  source_name: string
  excerpt: string
  score: number
}

export interface AIMessage {
  message_id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  citations: AICitation[]
  created_at: string
  mode?: string
}

export interface AISession {
  session_id: string
  mode: AILearningMode
  user_api_key: string
  llm_base_url?: string
  llm_model?: string
  marked_source_ids: string[]
  summary_artifact_id?: string
  created_at: string
  messages?: AIMessage[]
}

export interface AISessionCreateResponse {
  session_id: string
  mode: AILearningMode
}

export interface AISummaryResult {
  artifact_id: string
  title: string
  content: string
}
