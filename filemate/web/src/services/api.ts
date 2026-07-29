import axios from 'axios'
import type {
  ProcessingSession,
  ApiResponse,
  UploadResponse,
  ConfirmRequest,
  ConfirmResponse,
  HistoryItem
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

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
    console.error('[API Error]', error.message)
    return Promise.reject(error)
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

export default api