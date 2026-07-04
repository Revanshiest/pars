import { useCallback, useEffect, useRef, useState } from 'react'
import { Bot, Loader2, Send, Sparkles, User, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const STARTERS = [
  'Какой содержание Cu в руде Cerro Verde?',
  'Какая годовая переработка руды на Cerro Verde?',
  'Что такое flash smelting?',
  'Сравни отечественную и мировую практику электроэкстракции меди',
  'Какие свойства есть у меди?',
]

function SourceChip({ item }) {
  const value = item.value || item.raw?.properties?.value
  const answer = item.answer || item.description || item.snippet
  const src = item.metadata?.source_document || item.raw?.source_document
  const entity = item.raw?.subject || item.title?.split(' —[')[0]

  return (
    <div className="rounded-xl border border-surface-700 bg-surface-900/50 p-3 text-xs">
      <p className="font-semibold text-surface-200 leading-snug">{item.title}</p>
      {value && <p className="text-brand-600 font-bold mt-1">{value}</p>}
      {answer && answer !== value && (
        <p className="text-surface-400 mt-1 line-clamp-2">{answer}</p>
      )}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {src && <span className="text-[10px] text-surface-500">{src}</span>}
        {entity && (
          <Link
            to={`/graph?entity=${encodeURIComponent(entity)}`}
            className="text-[10px] text-brand-600 hover:underline"
          >
            Граф →
          </Link>
        )}
      </div>
    </div>
  )
}

function AssistantMessage({ msg }) {
  const [showSources, setShowSources] = useState(false)
  const sources = msg.sources || []

  return (
    <div className="flex gap-3 max-w-3xl">
      <div className="w-8 h-8 rounded-xl bg-brand-100 border border-brand-200 flex items-center justify-center shrink-0">
        <Bot size={16} className="text-brand-600" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="card p-4">
          <p className="text-sm text-surface-100 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
          {msg.confidence != null && (
            <p className="text-[10px] text-surface-400 mt-3">
              Уверенность ~{Math.round(msg.confidence * 100)}%
              {msg.llm_synthesized ? ' · LLM' : ' · база знаний'}
            </p>
          )}
        </div>
        {sources.length > 0 && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setShowSources(v => !v)}
              className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium"
            >
              {showSources ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Источники ({sources.length})
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {sources.slice(0, 8).map((s, i) => (
                  <SourceChip key={`${s.id || s.title}-${i}`} item={s} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function UserMessage({ content }) {
  return (
    <div className="flex gap-3 max-w-3xl ml-auto flex-row-reverse">
      <div className="w-8 h-8 rounded-xl bg-surface-800 border border-surface-700 flex items-center justify-center shrink-0">
        <User size={16} className="text-surface-300" />
      </div>
      <div className="card p-4 bg-brand-50 border-brand-100">
        <p className="text-sm text-surface-100 leading-relaxed">{content}</p>
      </div>
    </div>
  )
}

export default function SearchPage() {
  const { auth } = useAuth()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  const scrollDown = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollDown()
  }, [messages, loading, scrollDown])

  const send = async (text) => {
    const question = (text ?? input).trim()
    if (question.length < 2 || loading) return

    setInput('')
    setError('')
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const data = await api.agentSearch(auth, question)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer,
        sources: data.sources || data.ranked_results || [],
        confidence: data.confidence,
        llm_synthesized: data.llm_synthesized,
      }])
    } catch (err) {
      setError(err.message)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Не удалось получить ответ: ${err.message}`,
        sources: [],
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const onSubmit = (e) => {
    e.preventDefault()
    send()
  }

  return (
    <div className="flex flex-col mx-auto max-w-4xl" style={{ height: 'calc(100vh - 8rem)' }}>
      {/* Header */}
      <div className="shrink-0 mb-4">
        <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
          <Sparkles size={20} className="text-brand-600" />
          Ассистент базы знаний
        </h2>
        <p className="text-xs text-surface-400 mt-1">
          Задайте вопрос — ассистент найдёт факты в базе и сформулирует ответ
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 min-h-0">
        {messages.length === 0 && !loading && (
          <div className="card p-6 text-center">
            <Bot size={32} className="mx-auto text-brand-400 mb-3" />
            <p className="text-sm text-surface-300 mb-4">
              Спросите о процессах, материалах, предприятиях или параметрах из загруженных документов
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {STARTERS.map(q => (
                <button
                  key={q}
                  type="button"
                  className="badge bg-brand-50 text-brand-700 border border-brand-100 cursor-pointer hover:bg-brand-100 text-left"
                  onClick={() => send(q)}
                >
                  {q.length > 48 ? q.slice(0, 47) + '…' : q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          msg.role === 'user'
            ? <UserMessage key={i} content={msg.content} />
            : <AssistantMessage key={i} msg={msg} />
        ))}

        {loading && (
          <div className="flex gap-3 max-w-3xl">
            <div className="w-8 h-8 rounded-xl bg-brand-100 border border-brand-200 flex items-center justify-center shrink-0">
              <Bot size={16} className="text-brand-600" />
            </div>
            <div className="card p-4 flex items-center gap-2 text-sm text-surface-400">
              <Loader2 size={16} className="animate-spin-slow text-brand-600" />
              Ищу в базе знаний…
            </div>
          </div>
        )}

        {error && messages.length > 0 && (
          <p className="text-xs text-red-500 text-center">{error}</p>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} className="shrink-0 mt-4 card p-3 flex gap-2 items-end">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="Ваш вопрос… (Enter — отправить, Shift+Enter — новая строка)"
          rows={1}
          className={clsx(
            'input flex-1 resize-none min-h-[44px] max-h-32 py-3',
            loading && 'opacity-60',
          )}
          disabled={loading}
        />
        <button type="submit" className="btn-primary shrink-0 h-[44px]" disabled={loading || input.trim().length < 2}>
          {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <Send size={16} />}
        </button>
      </form>
    </div>
  )
}
