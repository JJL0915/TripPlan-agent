import axios from 'axios'
import type { AssistantChatRequest, AssistantChatResponse, TripFormData, TripPlanResponse } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

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
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
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
      await onEvent(JSON.parse(trimmed) as AssistantStreamEvent)
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    await onEvent(JSON.parse(buffer.trim()) as AssistantStreamEvent)
  }
}

export default apiClient
