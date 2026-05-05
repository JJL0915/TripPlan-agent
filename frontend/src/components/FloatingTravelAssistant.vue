<template>
  <div class="travel-assistant">
    <button v-if="!open" class="assistant-fab" type="button" title="行程问答助手" @click="open = true">
      <CustomerServiceOutlined />
    </button>

    <section v-else class="assistant-panel" aria-label="行程问答助手">
      <header class="assistant-header">
        <div class="assistant-title">
          <div class="assistant-avatar">
            <CustomerServiceOutlined />
          </div>
          <div>
            <h3>智能旅行问答助手</h3>
            <p>{{ pageTitle }}</p>
          </div>
        </div>
        <div class="assistant-actions">
          <button type="button" title="最小化" @click="open = false">
            <MinusOutlined />
          </button>
          <button type="button" title="清空会话" @click="resetChat">
            <ReloadOutlined />
          </button>
        </div>
      </header>

      <main ref="messagesRef" class="assistant-messages">
        <div class="time-divider">今天</div>
        <div
          v-for="(item, index) in messages"
          :key="index"
          class="message-row"
          :class="item.role"
        >
          <div v-if="item.role === 'assistant'" class="mini-avatar">
            <CustomerServiceOutlined />
          </div>
          <div class="message-bubble">
            {{ item.content }}
          </div>
        </div>
      </main>

      <div v-if="draftSummary" class="draft-summary">
        {{ draftSummary }}
      </div>

      <div class="quick-actions">
        <button type="button" @click="sendQuick('根据我现在的信息，帮我生成旅行计划')">
          推荐路线
        </button>
        <button type="button" @click="sendQuick('帮我优化预算，尽量降低费用')">
          预算建议
        </button>
        <button type="button" @click="sendQuick('当地有什么美食推荐？')">
          当地美食
        </button>
        <button type="button" @click="sendQuick('这份行程交通方便吗？')">
          交通攻略
        </button>
      </div>

      <form class="assistant-input" @submit.prevent="sendMessage">
        <textarea
          v-model="input"
          :disabled="loading"
          rows="1"
          placeholder="输入你的旅行问题..."
          @keydown.enter.prevent="sendMessage"
        />
        <button type="submit" :disabled="loading || !input.trim()" title="发送">
          <LoadingOutlined v-if="loading" />
          <SendOutlined v-else />
        </button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message as antMessage } from 'ant-design-vue'
import {
  CustomerServiceOutlined,
  LoadingOutlined,
  MinusOutlined,
  ReloadOutlined,
  SendOutlined
} from '@ant-design/icons-vue'
import { streamTravelAssistant } from '@/services/api'
import type { AssistantMessage, TripFormData, TripPlan } from '@/types'

const route = useRoute()
const router = useRouter()

const open = ref(false)
const loading = ref(false)
const input = ref('')
const messagesRef = ref<HTMLElement | null>(null)
const messages = ref<AssistantMessage[]>([
  {
    role: 'assistant',
    content: '你好，我可以帮你查询旅行信息、补全规划需求，也可以在生成计划后继续帮你修改行程。'
  }
])

const page = computed(() => (route.path === '/result' ? 'result' : 'planning'))
const pageTitle = computed(() => (page.value === 'result' ? '可根据当前行程继续问答或修改' : '可边聊边收集需求并生成计划'))

const draftSummary = computed(() => {
  const draft = getDraftTripRequest()
  if (!draft.city && !draft.start_date && !draft.end_date) return ''
  return `草稿：${draft.city || '未定目的地'} ${draft.start_date || '?'} 至 ${draft.end_date || '?'}`
})

const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

const setAssistantContent = async (index: number, content: string) => {
  messages.value[index] = {
    ...messages.value[index],
    content
  }
  await scrollToBottom()
}

const appendAssistantText = async (index: number, text: string) => {
  for (const char of text) {
    const current = messages.value[index]?.content || ''
    await setAssistantContent(index, current + char)
    await sleep(35)
  }
}

const appendAssistantNotice = async (content: string) => {
  const index = messages.value.length
  messages.value.push({ role: 'assistant', content: '' })
  await appendAssistantText(index, content)
}

const sendQuick = (text: string) => {
  input.value = text
  sendMessage()
}

const resetChat = () => {
  messages.value = [
    {
      role: 'assistant',
      content: '会话已重置。你可以继续告诉我旅行目的地、日期、偏好或想修改的地方。'
    }
  ]
}

const getPendingNotice = (content: string): string => {
  const generatePattern = /(生成|规划|制定|安排|推荐路线|开始|就这样|按这个|帮我做|出一份|做一份|旅行计划|行程计划)/
  const modifyPattern = /(修改|更改|调整|优化|替换|换成|删除|去掉|减少|增加|改成|重新安排|不想|太累|太贵|预算)/

  if (page.value === 'result' && modifyPattern.test(content)) {
    return '好的，我开始根据你的要求修改当前行程，完成后会把新的安排更新到页面里。'
  }

  const draft = getDraftTripRequest()
  const hasRequiredDraft = Boolean(draft.city && draft.start_date && draft.end_date)
  if (page.value === 'planning' && (generatePattern.test(content) || hasRequiredDraft)) {
    return '好的，我开始根据目前收集到的信息生成旅行计划，这一步需要查询景点、天气和酒店数据，请稍等。'
  }

  return ''
}

const sendMessage = async () => {
  const content = input.value.trim()
  if (!content || loading.value) return

  const history = messages.value.slice(-10)
  messages.value.push({ role: 'user', content })

  const pendingNotice = getPendingNotice(content)
  const assistantIndex = messages.value.length
  messages.value.push({ role: 'assistant', content: '' })

  input.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    if (pendingNotice) {
      await appendAssistantText(assistantIndex, pendingNotice)
    }

    let startedReply = false
    let replyIndex = assistantIndex
    await streamTravelAssistant(
      {
        message: content,
        page: page.value,
        history,
        draft_trip_request: getDraftTripRequest(),
        current_trip_plan: getCurrentTripPlan()
      },
      async (event) => {
        if (event.event === 'status') {
          if (!startedReply && !pendingNotice) {
            await setAssistantContent(replyIndex, event.message)
          }
          return
        }

        if (event.event === 'delta') {
          if (!startedReply) {
            startedReply = true
            if (pendingNotice) {
              replyIndex = messages.value.length
              messages.value.push({ role: 'assistant', content: '' })
              await scrollToBottom()
            } else {
              await setAssistantContent(replyIndex, '')
            }
          }
          await appendAssistantText(replyIndex, event.text)
          return
        }

        if (event.event === 'final') {
          const response = event.data
          if (response.draft_trip_request) {
            saveDraftTripRequest(response.draft_trip_request)
          }

          if (response.trip_plan) {
            saveTripPlan(response.trip_plan)
            const completionNotice = response.should_modify_plan
              ? '行程已修改完毕，页面里的新安排已经更新好了。'
              : response.should_generate_plan
                ? '旅行计划已生成完毕，请在页面中查看完整行程。'
                : ''

            if (response.should_generate_plan && route.path !== '/result') {
              await router.push('/result')
            }

            if (completionNotice) {
              await appendAssistantNotice(completionNotice)
            }
          }

          if (!response.success) {
            antMessage.warning(response.message || '助手暂时没有完成这次操作')
          }
          return
        }

        if (event.event === 'error') {
          if (pendingNotice && !startedReply) {
            await appendAssistantNotice(event.message)
          } else {
            await setAssistantContent(replyIndex, event.message)
          }
          antMessage.error(event.message)
        }
      }
    )
  } catch (error: any) {
    await setAssistantContent(assistantIndex, error.message || '助手服务暂时不可用，请稍后再试。')
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const getDraftTripRequest = (): Partial<TripFormData> => {
  const raw = sessionStorage.getItem('assistantDraftTripRequest')
  if (!raw) return {}
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

const saveDraftTripRequest = (draft: Partial<TripFormData>) => {
  sessionStorage.setItem('assistantDraftTripRequest', JSON.stringify(draft))
  window.dispatchEvent(new CustomEvent('assistant:draft-updated', { detail: draft }))
}

const getCurrentTripPlan = (): TripPlan | null => {
  const raw = sessionStorage.getItem('tripPlan')
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

const saveTripPlan = (plan: TripPlan) => {
  sessionStorage.setItem('tripPlan', JSON.stringify(plan))
  window.dispatchEvent(new CustomEvent('assistant:trip-updated', { detail: plan }))
}

onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.travel-assistant {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 1000;
}

.assistant-fab {
  width: 68px;
  height: 68px;
  border: 2px solid rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  color: white;
  font-size: 30px;
  background: linear-gradient(135deg, #4f7cff 0%, #7a43b6 100%);
  box-shadow: 0 14px 36px rgba(54, 67, 140, 0.35);
  cursor: pointer;
}

.assistant-panel {
  width: min(430px, calc(100vw - 32px));
  height: min(720px, calc(100vh - 48px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(110, 116, 180, 0.18);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 24px 70px rgba(34, 42, 92, 0.32);
  backdrop-filter: blur(18px);
}

.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 18px 14px;
  border-bottom: 1px solid #eceef7;
}

.assistant-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.assistant-avatar,
.mini-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
  background: linear-gradient(135deg, #4f7cff 0%, #7a43b6 100%);
}

.assistant-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  font-size: 24px;
}

.mini-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 15px;
}

.assistant-title h3 {
  margin: 0;
  color: #29314d;
  font-size: 16px;
  font-weight: 700;
}

.assistant-title p {
  margin: 2px 0 0;
  color: #7c849c;
  font-size: 12px;
}

.assistant-actions {
  display: flex;
  gap: 8px;
}

.assistant-actions button {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  color: #606987;
  background: transparent;
  cursor: pointer;
}

.assistant-actions button:hover {
  background: #f1f3fb;
}

.assistant-messages {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
  background: linear-gradient(180deg, rgba(248, 249, 255, 0.9) 0%, rgba(255, 255, 255, 0.96) 100%);
}

.time-divider {
  margin: 0 auto 14px;
  color: #9aa3b8;
  font-size: 12px;
  text-align: center;
}

.message-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 78%;
  padding: 12px 14px;
  border-radius: 12px;
  color: #27304a;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: white;
  box-shadow: 0 8px 22px rgba(31, 42, 92, 0.08);
}

.message-row.user .message-bubble {
  color: white;
  background: linear-gradient(135deg, #4f7cff 0%, #7a43b6 100%);
}

.draft-summary {
  margin: 0 16px 10px;
  padding: 8px 10px;
  border: 1px solid #e7e9f5;
  border-radius: 10px;
  color: #596278;
  font-size: 12px;
  background: #fbfcff;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 0 16px 12px;
}

.quick-actions button {
  min-width: 0;
  height: 32px;
  border: 1px solid #dfe3f2;
  border-radius: 16px;
  color: #596278;
  background: white;
  font-size: 12px;
  cursor: pointer;
}

.quick-actions button:hover {
  color: #4f63c7;
  border-color: #b8c1f1;
}

.assistant-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px 18px;
  border-top: 1px solid #eceef7;
}

.assistant-input textarea {
  flex: 1;
  min-height: 44px;
  max-height: 100px;
  resize: none;
  border: 1px solid #e1e5f2;
  border-radius: 12px;
  padding: 11px 12px;
  color: #27304a;
  outline: none;
}

.assistant-input textarea:focus {
  border-color: #6477df;
  box-shadow: 0 0 0 3px rgba(100, 119, 223, 0.12);
}

.assistant-input button {
  width: 46px;
  height: 46px;
  border: 0;
  border-radius: 50%;
  color: white;
  font-size: 18px;
  background: linear-gradient(135deg, #4f7cff 0%, #7a43b6 100%);
  cursor: pointer;
}

.assistant-input button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .travel-assistant {
    right: 16px;
    bottom: 16px;
  }

  .assistant-panel {
    height: min(660px, calc(100vh - 32px));
  }

  .quick-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
