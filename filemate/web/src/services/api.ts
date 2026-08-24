import axios from 'axios'
import type {
  ProcessingSession,
  ApiResponse,
  UploadResponse,
  ConfirmRequest,
  ConfirmResponse,
  HistoryItem,
  UndoResponse,
  ExecutionRecord
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 120000, // 2分钟超时（AI生成需要更长时间）
  headers: {
    'Content-Type': 'application/json'
  }
})

export async function checkHealth(): Promise<boolean> {
  const response = await api.get<any, ApiResponse<{ version: string }>>('/api/health')
  return response.success && response.data?.version === '1.2.0'
}

// 请求拦截器
api.interceptors.request.use(
  config => {
    console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`)
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    const message =
      error.response?.data?.error ||
      error.response?.data?.detail ||
      error.message ||
      '请求失败'
    console.error('[API Error]', message)
    return Promise.reject(new Error(message))
  }
)

// 上传文件
export async function uploadFile(file: File): Promise<ProcessingSession> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post<any, ApiResponse<UploadResponse>>(
    '/process',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '文件处理失败')
}

// 获取 Session
export async function getSession(sessionId: string): Promise<ProcessingSession> {
  const response = await api.get<any, ApiResponse<ProcessingSession>>(
    `/sessions/${sessionId}`
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '获取会话失败')
}

// 保存草稿修改，不触发文件移动
export async function updateSessionDraft(
  sessionId: string,
  edits: Record<string, any>
): Promise<ProcessingSession> {
  const response = await api.patch<any, ApiResponse<ProcessingSession>>(
    `/sessions/${sessionId}`,
    { edits }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '保存修改失败')
}

// 确认/拒绝
export async function confirmSession(
  sessionId: string,
  data: ConfirmRequest
): Promise<ConfirmResponse> {
  const response = await api.post<any, ApiResponse<ConfirmResponse>>(
    `/sessions/${sessionId}/confirm`,
    data
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '确认失败')
}

// 撤销已执行的归档与日历写入
export async function undoSession(sessionId: string): Promise<UndoResponse> {
  const response = await api.post<any, ApiResponse<UndoResponse>>(
    `/sessions/${sessionId}/undo`
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '撤销失败')
}

export async function getSessionExecutions(
  sessionId: string
): Promise<ExecutionRecord[]> {
  const response = await api.get<any, ApiResponse<ExecutionRecord[]>>(
    `/sessions/${sessionId}/executions`
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '获取执行记录失败')
}

// 获取历史记录
export async function getHistory(
  status?: string,
  limit: number = 20
): Promise<HistoryItem[]> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  params.append('limit', String(limit))

  const response = await api.get<any, ApiResponse<HistoryItem[]>>(
    `/sessions?${params.toString()}`
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '获取历史记录失败')
}

// 获取 .ics 内容
export async function getIcsContent(sessionId: string): Promise<string> {
  const response = await api.get<any, ApiResponse<string>>(
    `/sessions/${sessionId}/ics`
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '获取 ICS 失败')
}

// 下载 .ics 文件
export function downloadIcs(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// =============== AI 工具箱 API ===============

// AI摘要生成
export interface AISummaryRequest {
  file: File
  max_length?: number
}

export interface AISummaryResponse {
  ctx_id: string
  filename: string
  summary: string
  text_length: number
}

export async function generateSummary(
  file: File,
  max_length: number = 500
): Promise<AISummaryResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('max_length', String(max_length))

  const response = await api.post<any, ApiResponse<AISummaryResponse>>(
    '/ai/summarize',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '摘要生成失败')
}

// AI知识卡生成
export interface KnowledgeCard {
  front: string
  back: string
}

export interface AIKnowledgeCardsRequest {
  file: File
  num_cards?: number
  card_format?: string
}

export interface AIKnowledgeCardsResponse {
  ctx_id: string
  filename: string
  cards: KnowledgeCard[]
  cards_count: number
}

export async function generateKnowledgeCards(
  file: File,
  num_cards: number = 10,
  card_format: string = 'front_back'
): Promise<AIKnowledgeCardsResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('num_cards', String(num_cards))
  formData.append('card_format', card_format)

  const response = await api.post<any, ApiResponse<AIKnowledgeCardsResponse>>(
    '/ai/knowledge-cards',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '知识卡生成失败')
}

// AI题目提取
export interface AIQuestion {
  type: string
  question: string
  options?: string[]
  answer: string
  explanation?: string
}

export interface AIQuestionsRequest {
  file: File
  question_types?: string
  num_questions?: number
}

export interface AIQuestionsResponse {
  ctx_id: string
  filename: string
  questions: AIQuestion[]
  questions_count: number
  source_id: string
  artifact_id: string
}

export async function extractQuestions(
  file: File,
  question_types?: string,
  num_questions: number = 10
): Promise<AIQuestionsResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('num_questions', String(num_questions))
  if (question_types) {
    formData.append('question_types', question_types)
  }

  const response = await api.post<any, ApiResponse<AIQuestionsResponse>>(
    '/ai/questions',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '题目提取失败')
}

// AI笔记提取
export interface AINoteSection {
  title: string
  content: string | string[]
}

export interface AINotes {
  title: string
  sections: AINoteSection[]
  format: string
}

export interface AINotesRequest {
  file: File
  format?: string
}

export interface AINotesResponse {
  ctx_id: string
  filename: string
  notes: AINotes
}

export async function extractNotes(
  file: File,
  format: string = 'outline'
): Promise<AINotesResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('format', format)

  const response = await api.post<any, ApiResponse<AINotesResponse>>(
    '/ai/notes',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '笔记提取失败')
}

// AI问答
export interface AIChatRequest {
  ctx_id: string
  question: string
  chat_history?: Array<{ role: string; content: string }>
  mode?: 'answer' | 'socratic' | 'feynman'
}

export interface AIChatResponse {
  ctx_id: string
  question: string
  answer: string
  mode: 'answer' | 'socratic' | 'feynman'
  citations: Array<{
    id: number
    source_name: string
    page_number?: number
    chunk_index: number
    excerpt: string
  }>
  chat_history: Array<{ role: string; content: string }>
}

export async function askAI(
  ctx_id: string,
  question: string,
  chat_history?: Array<{ role: string; content: string }>,
  mode: 'answer' | 'socratic' | 'feynman' = 'answer'
): Promise<AIChatResponse> {
  const response = await api.post<any, ApiResponse<AIChatResponse>>(
    '/ai/chat',
    {
      ctx_id,
      question,
      chat_history,
      mode
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || 'AI问答失败')
}

export interface QuizAttemptResult {
  attempt_id: string
  is_correct: boolean
  score: number
  feedback: string
  reference_answer: string
}

export async function submitQuizAttempt(
  artifactId: string,
  questionIndex: number,
  userAnswer: string
): Promise<QuizAttemptResult> {
  const response = await api.post<any, ApiResponse<QuizAttemptResult>>(
    '/quiz/attempts',
    { artifact_id: artifactId, question_index: questionIndex, user_answer: userAnswer }
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '提交答案失败')
}

export interface WrongQuestion {
  wrong_id: string
  artifact_id: string
  question_index: number
  question: AIQuestion
  latest_answer: string
  error_count: number
  correct_streak: number
  mastered: number
  next_review_at: string
  interval_days: number
  ease_factor: number
  review_count: number
  updated_at: string
}

export async function getWrongbook(mastered: boolean = false): Promise<WrongQuestion[]> {
  const response = await api.get<any, ApiResponse<WrongQuestion[]>>(
    `/wrongbook?mastered=${mastered}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '获取错题本失败')
}

export interface InterviewEvaluation {
  score: number
  dimensions: Record<string, number>
  feedback: string
}

export interface InterviewTurn {
  turn_id: string
  question_index: number
  question: string
  answer: string
  score: number
  dimensions: Record<string, number>
  feedback: string
}

export interface InterviewSession {
  interview_id: string
  target_role: string
  scenario: string
  difficulty: string
  status: 'active' | 'completed'
  questions: string[]
  current_index: number
  current_question: string | null
  overall_score: number
  turns: InterviewTurn[]
  latest_evaluation?: InterviewEvaluation
}

export async function startInterview(
  targetRole: string,
  scenario: string,
  difficulty: string
): Promise<InterviewSession> {
  const response = await api.post<any, ApiResponse<InterviewSession>>('/interviews', {
    target_role: targetRole,
    scenario,
    difficulty
  })
  if (response.success && response.data) return response.data
  throw new Error(response.error || '创建模拟面试失败')
}

export async function answerInterview(
  interviewId: string,
  answer: string
): Promise<InterviewSession> {
  const response = await api.post<any, ApiResponse<InterviewSession>>(
    `/interviews/${interviewId}/answers`,
    { answer }
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '面试回答评分失败')
}

export interface LearningAnalytics {
  source_count: number
  artifact_count: number
  pending_wrong_count: number
  mastered_wrong_count: number
  quiz_attempt_count: number
  study_plan_count: number
  completed_study_plan_count: number
  total_study_days: number
  completed_study_days: number
  study_completion_rate: number
  product_feedback: {
    total: number
    positive: number
    positive_rate: number
    by_area: Record<string, { total: number; positive: number; positive_rate: number }>
  }
  interview_count: number
  average_interview_score: number
  interview_dimensions: Record<string, number>
  recent_interviews: Array<{
    interview_id: string
    target_role: string
    scenario: string
    status: string
    current_index: number
    overall_score: number
    created_at: string
  }>
}

export async function getLearningAnalytics(): Promise<LearningAnalytics> {
  const response = await api.get<any, ApiResponse<LearningAnalytics>>('/analytics/overview')
  if (response.success && response.data) return response.data
  throw new Error(response.error || '获取成长数据失败')
}

export interface TodayReviewItem {
  item_id: string
  kind: 'plan_day' | 'wrong_question'
  priority: 'high' | 'normal'
  title: string
  reason: string
  duration_minutes: number
  tasks?: string[]
  plan_id?: string
  day_index?: number
  artifact_id?: string
  question_index?: number
  wrong_id?: string
  explanation?: string
  route: string
}

export interface TodayReview {
  date: string
  items: TodayReviewItem[]
  active_plan_count: number
  pending_wrong_count: number
  recommended_minutes: number
}

export async function getTodayReview(): Promise<TodayReview> {
  const response = await api.get<any, ApiResponse<TodayReview>>('/review/today')
  if (response.success && response.data) return response.data
  throw new Error(response.error || '今日学习任务加载失败')
}

export type FeedbackArea = 'retrieval' | 'tutor' | 'interview' | 'study_plan'

export async function submitProductFeedback(
  area: FeedbackArea,
  targetId: string,
  rating: -1 | 1,
  context: Record<string, number | string> = {}
): Promise<void> {
  const response = await api.post<any, ApiResponse<{ feedback_id: string }>>(
    '/evaluation/feedback',
    { area, target_id: targetId, rating, context }
  )
  if (!response.success) throw new Error(response.error || '反馈保存失败')
}

export async function downloadAnonymousFeedback(): Promise<void> {
  const blob = await api.get<any, Blob>('/evaluation/feedback/export.csv', {
    responseType: 'blob'
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'filemate-anonymous-feedback.csv'
  link.click()
  URL.revokeObjectURL(url)
}

export interface KnowledgeSource {
  source_id: string
  original_name: string
  media_type: string
  text_length: number
  metadata: Record<string, any>
  created_at: string
}

export interface KnowledgeArtifact {
  artifact_id: string
  source_id: string | null
  artifact_type: string
  title: string
  content: any
  metadata: Record<string, any>
  created_at: string
  updated_at: string
}

export interface KnowledgeSearchResult {
  chunk_id: string
  source_id: string
  source_name: string
  page_number?: number
  chunk_index: number
  excerpt: string
  score: number
}

export async function getKnowledgeSources(limit = 100): Promise<KnowledgeSource[]> {
  const response = await api.get<any, ApiResponse<KnowledgeSource[]>>(
    `/knowledge/sources?limit=${limit}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '获取知识库失败')
}

export interface SourceDeletionResult {
  source_id: string
  affected: {
    artifacts: number
    chunks: number
    contexts: number
    quiz_attempts: number
    wrong_questions: number
    study_plans: number
  }
  managed_file: {
    path: string | null
    managed: boolean
    exists: boolean
    removed: boolean
  }
  external_files_untouched: boolean
}

export async function deleteKnowledgeSource(sourceId: string): Promise<SourceDeletionResult> {
  const response = await api.delete<any, ApiResponse<SourceDeletionResult>>(
    `/knowledge/sources/${sourceId}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '删除资料失败')
}

export async function getKnowledgeArtifacts(sourceId: string): Promise<KnowledgeArtifact[]> {
  const response = await api.get<any, ApiResponse<KnowledgeArtifact[]>>(
    `/knowledge/sources/${sourceId}/artifacts`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '获取学习产物失败')
}

export async function getKnowledgeArtifact(artifactId: string): Promise<KnowledgeArtifact> {
  const response = await api.get<any, ApiResponse<KnowledgeArtifact>>(
    `/knowledge/artifacts/${artifactId}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '获取学习产物详情失败')
}

export async function updateKnowledgeArtifact(
  artifactId: string,
  title: string,
  content: any
): Promise<KnowledgeArtifact> {
  const response = await api.patch<any, ApiResponse<KnowledgeArtifact>>(
    `/knowledge/artifacts/${artifactId}`,
    { title, content }
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '学习产物保存失败')
}

export async function searchKnowledge(
  query: string,
  sourceId?: string
): Promise<KnowledgeSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: '8' })
  if (sourceId) params.set('source_id', sourceId)
  const response = await api.get<any, ApiResponse<KnowledgeSearchResult[]>>(
    `/knowledge/search?${params.toString()}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '检索知识库失败')
}

// AI 个性化学习计划
export interface StudyTopic {
  name: string
  priority: 'high' | 'medium' | 'low'
  reason: string
}

export interface StudyDay {
  date: string
  focus: string
  tasks: string[]
  duration_minutes: number
  review_method: string
}

export interface StudyCheckpoint {
  date: string
  goal: string
}

export interface StudyPlan {
  title: string
  exam_date: string
  total_days: number
  daily_minutes: number
  goal: string
  strategy: string
  topics: StudyTopic[]
  daily_plan: StudyDay[]
  checkpoints: StudyCheckpoint[]
}

export interface AIStudyPlanResponse {
  ctx_id: string
  filename: string
  plan: StudyPlan
  source_id: string
  artifact_id: string
  plan_id: string
  completed_days: number[]
}

export interface StudyPlanRecord {
  plan_id: string
  artifact_id: string
  source_id: string | null
  title: string
  exam_date: string
  daily_minutes: number
  goal: string
  plan_data: StudyPlan
  completed_days: number[]
  status: 'active' | 'completed' | 'archived'
  created_at: string
  updated_at: string
}

export async function generateStudyPlan(
  file: File,
  examDate: string,
  dailyMinutes: number,
  goal: string,
  weakTopics?: string
): Promise<AIStudyPlanResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('exam_date', examDate)
  formData.append('daily_minutes', String(dailyMinutes))
  formData.append('goal', goal)
  if (weakTopics?.trim()) {
    formData.append('weak_topics', weakTopics.trim())
  }

  const response = await api.post<any, ApiResponse<AIStudyPlanResponse>>(
    '/ai/study-plan',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  if (response.success && response.data) {
    return response.data
  }
  throw new Error(response.error || '学习计划生成失败')
}

export async function getStudyPlans(
  status?: StudyPlanRecord['status'],
  limit = 20
): Promise<StudyPlanRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  const response = await api.get<any, ApiResponse<StudyPlanRecord[]>>(
    `/study-plans?${params.toString()}`
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '学习计划加载失败')
}

export async function updateStudyPlanDay(
  planId: string,
  dayIndex: number,
  completed: boolean
): Promise<StudyPlanRecord> {
  const response = await api.patch<any, ApiResponse<StudyPlanRecord>>(
    `/study-plans/${planId}/days/${dayIndex}`,
    { completed }
  )
  if (response.success && response.data) return response.data
  throw new Error(response.error || '学习进度保存失败')
}
