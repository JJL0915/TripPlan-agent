import axios from 'axios'
import type {
  AssistantChatRequest,
  AssistantChatResponse,
  AssistantSessionResponse,
  TripFormData,
  TripPlan,
  TripPlanResponse,
  TripPlanUpdateRequest
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const SESSION_ID_KEY = 'assistantSessionId'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const startTime = Date.now()
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    const elapsed = (Date.now() - startTime) / 1000
    console.log(`请求耗时 ${elapsed.toFixed(1)}s, 响应:`, response.data)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    if (error.code === 'ECONNABORTED') {
      throw new Error('请求超时，Agent 生成耗时过长，请稍后重试或简化需求')
    }
    throw new Error(getApiErrorMessage(error, '生成旅行计划失败'))
  }
}

export function getAssistantSessionId(): string {
  return sessionStorage.getItem(SESSION_ID_KEY) || ''
}

export function saveAssistantSessionId(sessionId?: string | null) {
  if (!sessionId) return
  sessionStorage.setItem(SESSION_ID_KEY, sessionId)
}

export function clearAssistantSessionId() {
  sessionStorage.removeItem(SESSION_ID_KEY)
}

function rememberSession(data: { session_id?: string | null }) {
  saveAssistantSessionId(data.session_id)
}

function getApiErrorMessage(error: any, fallback: string): string {
  const detail = error.response?.data?.detail
  return detail?.message || detail || error.message || fallback
}

export async function getAssistantSession(sessionId: string): Promise<AssistantSessionResponse> {
  const response = await apiClient.get<AssistantSessionResponse>(`/api/assistant/session/${sessionId}`)
  rememberSession(response.data)
  return response.data
}

export async function getSessionTripPlan(sessionId: string): Promise<TripPlanResponse> {
  const response = await apiClient.get<TripPlanResponse>(`/api/assistant/session/${sessionId}/trip-plan`)
  rememberSession(response.data)
  return response.data
}

export async function getAttractionPhoto(name: string): Promise<string | null> {
  try {
    const response = await apiClient.get('/api/poi/photo', { params: { name } })
    return response.data?.data?.photo_url || null
  } catch (error) {
    console.error(`获取${name}图片失败:`, error)
    return null
  }
}

export async function saveSessionTripPlan(
  sessionId: string,
  tripPlan: TripPlan,
  basePlanVersion: number
): Promise<TripPlanResponse> {
  const payload: TripPlanUpdateRequest = {
    trip_plan: tripPlan,
    base_plan_version: basePlanVersion
  }
  try {
    const response = await apiClient.put<TripPlanResponse>(
      `/api/assistant/session/${sessionId}/trip-plan`,
      payload
    )
    rememberSession(response.data)
    return response.data
  } catch (error: any) {
    throw new Error(getApiErrorMessage(error, '保存行程失败'))
  }
}

export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export type AssistantStreamEvent =
  | { event: 'status'; message: string }
  | { event: 'delta'; text: string }
  | { event: 'final'; data: AssistantChatResponse }
  | { event: 'error'; message: string }

export async function streamTravelAssistant(
  payload: AssistantChatRequest,
  onEvent: (event: AssistantStreamEvent) => void | Promise<void>
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/assistant/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })

  if (!response.ok || !response.body) {
    throw new Error(`助手流式请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const event = JSON.parse(trimmed) as AssistantStreamEvent
      if (event.event === 'final') {
        rememberSession(event.data)
      }
      await onEvent(event)
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    const event = JSON.parse(buffer.trim()) as AssistantStreamEvent
    if (event.event === 'final') {
      rememberSession(event.data)
    }
    await onEvent(event)
  }
}

export default apiClient
