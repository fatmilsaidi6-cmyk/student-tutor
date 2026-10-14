import { useEffect, useRef, useState } from 'react'
import Login from './components/Login.jsx'
import Markdown from './components/Markdown.jsx'
import { askFollowup, explainHomework } from './lib/api.js'
import {
  getAccessCode,
  loadHistory,
  loadPrefs,
  newId,
  saveAccessCode,
  saveHistory,
  savePrefs,
} from './lib/storage.js'
import './App.css'

const LEVELS = [
  { id: 'primary', label: 'Primary', emoji: '🌱' },
  { id: 'middle', label: 'Middle', emoji: '📚' },
  { id: 'high', label: 'High School', emoji: '🎓' },
  { id: 'university', label: 'University', emoji: '🏛️' },
]

const ENGINES = [
  { id: 'auto', label: 'Auto (smart)', hint: 'Cloud + local fallback' },
  { id: 'local', label: 'Local (private)', hint: 'Ollama, offline' },
  { id: 'cloud', label: 'Cloud (best)', hint: 'OpenRouter' },
]

const MAX_FILES = 10

function levelLabel(id) {
  return LEVELS.find((l) => l.id === id)?.label || id
}

function makeTitle(data, files) {
  const subject = data.subject?.trim()
  if (subject) return subject
  const firstLine = (data.explanation || '')
    .split('\n')
    .map((l) => l.trim())
    .find(Boolean)
  const clean = firstLine?.replace(/[#*_`$\\]/g, '').trim()
  if (clean) return clean.slice(0, 60)
  return files[0]?.name || 'Homework'
}

function toMarkdown(item) {
  const head =
    `# Study Buddy — ${item.subject || 'Homework'}\n\n` +
    `_Level: ${levelLabel(item.level)} · Read via ${item.readMethod} · ` +
    `Engine: ${item.engineUsed}_\n\n`
  let body = item.explanation || ''
  if (item.messages?.length) {
    body += '\n\n---\n\n## Follow-up discussion\n\n'
    for (const m of item.messages) {
      body += `**${m.role === 'user' ? 'You' : 'Tutor'}:** ${m.content}\n\n`
    }
  }
  return head + body
}

function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} h ago`
  return new Date(ts).toLocaleDateString()
}

function App() {
  const [level, setLevel] = useState(() => loadPrefs().level || 'high')
  const [engine, setEngine] = useState(() => loadPrefs().engine || 'auto')
  const [theme, setTheme] = useState(() => loadPrefs().theme || 'light')

  const [problem, setProblem] = useState('')
  const [subject, setSubject] = useState('')
  const [question, setQuestion] = useState('')
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [dragOver, setDragOver] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [history, setHistory] = useState(() => loadHistory())
  const [active, setActive] = useState(null)

  const [followupInput, setFollowupInput] = useState('')
  const [followupLoading, setFollowupLoading] = useState(false)
  const [followupError, setFollowupError] = useState('')

  const [toast, setToast] = useState('')
  const [serverDown, setServerDown] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [apiKeyRequired, setApiKeyRequired] = useState(false)
  const [oauthProviders, setOauthProviders] = useState([])
  const [user, setUser] = useState(null)
  const [authError, setAuthError] = useState('')
  const [accessCode, setAccessCode] = useState(() => getAccessCode())
  const [codeInput, setCodeInput] = useState(() => getAccessCode())
  const [showCode, setShowCode] = useState(false)
  const inputRef = useRef(null)

  const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp']

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    savePrefs({ level, engine, theme })
  }, [level, engine, theme])

  useEffect(() => {
    const urls = files.map((f) => (IMAGE_TYPES.includes(f.type) ? URL.createObjectURL(f) : null))
    setPreviews(urls)
    return () => urls.forEach((u) => u && URL.revokeObjectURL(u))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 1800)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams(window.location.search)
    const err = params.get('auth_error')
    if (err) {
      setAuthError(`Sign-in failed (${err}). Please try again.`)
      window.history.replaceState({}, '', window.location.pathname)
    }

    Promise.all([
      fetch('/api/health').then((r) => (r.ok ? r.json() : Promise.reject(new Error('bad')))),
      fetch('/api/auth/me').then((r) => (r.ok ? r.json() : {})),
    ])
      .then(([health, me]) => {
        if (cancelled) return
        setServerDown(false)
        setApiKeyRequired(!!health.api_key_required)
        setOauthProviders(health.oauth_providers || [])
        setUser(me.user || null)
        if (health.api_key_required && !me.user && !(health.oauth_providers || []).length) {
          setShowCode(true)
        }
      })
      .catch(() => {
        if (!cancelled) setServerDown(true)
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function saveCode(e) {
    e.preventDefault()
    const code = codeInput.trim()
    saveAccessCode(code)
    setAccessCode(code)
    setShowCode(false)
    setToast(code ? 'Access code saved' : 'Access code cleared')
  }

  async function logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } catch {
      /* ignore */
    }
    setUser(null)
    setActive(null)
  }

  function addFiles(list) {
    const incoming = Array.from(list || []).filter(Boolean)
    if (!incoming.length) return
    setError('')
    setActive(null)
    setFollowupInput('')
    setFiles((prev) => [...prev, ...incoming].slice(0, MAX_FILES))
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    addFiles(e.dataTransfer.files)
  }

  async function submit(e) {
    e.preventDefault()
    if (!problem.trim()) {
      setError('Type the problem or the work you want help with first.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await explainHomework({
        text: problem,
        files,
        level,
        subject,
        question,
        engine,
      })
      const item = {
        id: newId(),
        createdAt: Date.now(),
        title: makeTitle(data, files),
        level,
        subject: data.subject || '',
        fileNames: files.map((f) => f.name),
        fileCount: data.file_count || files.length,
        explanation: data.explanation,
        extractedText: data.extracted_text,
        readMethod: data.read_method,
        engineUsed: data.engine_used,
        messages: [],
      }
      setActive(item)
      setHistory((h) => {
        const next = [item, ...h]
        saveHistory(next)
        return next
      })
    } catch (err) {
      setError(err.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  function patchActive(patchOrFn) {
    setActive((cur) => {
      if (!cur) return cur
      const next = typeof patchOrFn === 'function' ? patchOrFn(cur) : { ...cur, ...patchOrFn }
      queueMicrotask(() => {
        setHistory((h) => {
          const nh = h.map((x) => (x.id === next.id ? next : x))
          saveHistory(nh)
          return nh
        })
      })
      return next
    })
  }

  async function submitFollowup(e) {
    e.preventDefault()
    const text = followupInput.trim()
    if (!text || !active || followupLoading) return

    const priorMessages = active.messages || []
    const userMsg = { role: 'user', content: text }
    const withUser = [...priorMessages, userMsg]
    patchActive({ messages: withUser })
    setFollowupInput('')
    setFollowupError('')
    setFollowupLoading(true)
    try {
      const data = await askFollowup({
        context: active.extractedText,
        messages: withUser,
        level: active.level,
        subject: active.subject,
        engine,
      })
      patchActive({ messages: [...withUser, { role: 'assistant', content: data.answer }] })
    } catch (err) {
      setFollowupError(err.message || String(err))
      patchActive({ messages: priorMessages })
      setFollowupInput(text)
    } finally {
      setFollowupLoading(false)
    }
  }

  function selectHistory(item) {
    setActive(item)
    setFiles([])
    setProblem('')
    setSubject('')
    setQuestion('')
    setError('')
    setFollowupInput('')
    setFollowupError('')
  }

  function newSession() {
    setActive(null)
    setFiles([])
    setProblem('')
    setSubject('')
    setQuestion('')
    setError('')
    setFollowupInput('')
    setFollowupError('')
  }

  function deleteHistory(e, id) {
    e.stopPropagation()
    setHistory((h) => {
      const next = h.filter((x) => x.id !== id)
      saveHistory(next)
      return next
    })
    if (active?.id === id) setActive(null)
  }

  async function copyAnswer() {
    if (!active) return
    try {
      await navigator.clipboard.writeText(toMarkdown(active))
      setToast('Copied to clipboard')
    } catch {
      setToast('Copy failed')
    }
  }

  function downloadAnswer() {
    if (!active) return
    const blob = new Blob([toMarkdown(active)], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `study-buddy-${active.id.slice(0, 6)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!authChecked) {
    return <div className="boot" aria-busy="true" />
  }

  if (oauthProviders.length > 0 && !user) {
    return (
      <div className="app">
        {serverDown && (
          <div className="banner">
            ⚠️ Can’t reach the backend. Start the server and reload this page.
          </div>
        )}
        <Login providers={oauthProviders} error={authError} />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">📘</span>
          <div>
            <h1>Study Buddy</h1>
            <p>Snap your homework, learn step by step.</p>
          </div>
        </div>
        <div className="topbar-actions">
          {apiKeyRequired && oauthProviders.length === 0 && (
            <button
              type="button"
              className={`ghost-btn ${accessCode ? 'unlocked' : ''}`}
              onClick={() => setShowCode((s) => !s)}
              title={accessCode ? 'Access code set' : 'Access code required'}
            >
              {accessCode ? '🔓' : '🔑'}
            </button>
          )}
          {user && (
            <div className="user-menu">
              {user.picture ? (
                <img className="avatar" src={user.picture} alt="" referrerPolicy="no-referrer" />
              ) : (
                <span className="avatar fallback">{(user.name || '?').charAt(0).toUpperCase()}</span>
              )}
              <span className="user-name" title={user.email}>
                {user.name || user.email}
              </span>
              <button type="button" className="mini-btn" onClick={logout}>
                Sign out
              </button>
            </div>
          )}
          <button
            type="button"
            className="ghost-btn"
            onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}
            title="Toggle theme"
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
      </header>

      {serverDown && (
        <div className="banner">
          ⚠️ Can’t reach the backend. Start the server, then open the app at{' '}
          <code>http://localhost:8000</code> — not by opening the HTML file directly.
        </div>
      )}

      {apiKeyRequired && oauthProviders.length === 0 && showCode && (
        <div className="banner auth">
          <span>
            {accessCode
              ? '🔒 Update the access code for this server:'
              : '🔒 This server requires an access code to use the tutor.'}
          </span>
          <form className="auth-form" onSubmit={saveCode}>
            <input
              type="password"
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value)}
              placeholder="Access code"
              autoComplete="off"
            />
            <button type="submit" className="mini-btn">
              Save
            </button>
          </form>
        </div>
      )}

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-head">
            <span>History</span>
            <button type="button" className="mini-btn" onClick={newSession}>
              + New
            </button>
          </div>
          {history.length === 0 ? (
            <p className="muted small">Your solved homework will appear here.</p>
          ) : (
            <ul className="history-list">
              {history.map((item) => (
                <li
                  key={item.id}
                  className={`history-item ${active?.id === item.id ? 'active' : ''}`}
                  onClick={() => selectHistory(item)}
                >
                  <div className="history-title">{item.title}</div>
                  <div className="history-meta">
                    <span>{levelLabel(item.level)}</span>
                    <span>·</span>
                    <span>{timeAgo(item.createdAt)}</span>
                  </div>
                  <button
                    type="button"
                    className="history-del"
                    onClick={(e) => deleteHistory(e, item.id)}
                    title="Delete"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="content">
          {!active ? (
            <form onSubmit={submit} className="panel config">
              <label className="problem-field">
                <span className="label">
                  Your problem or work <span className="req">(required)</span>
                </span>
                <textarea
                  value={problem}
                  onChange={(e) => setProblem(e.target.value)}
                  placeholder="Type the question, the problem, or what you've tried so far…&#10;e.g. Solve 2x + 3 = 11 and explain each step"
                  rows={4}
                  required
                />
              </label>

              <fieldset>
                <legend>Your level</legend>
                <div className="level-row">
                  {LEVELS.map((l) => (
                    <button
                      type="button"
                      key={l.id}
                      className={`level-btn ${level === l.id ? 'active' : ''}`}
                      onClick={() => setLevel(l.id)}
                    >
                      <span className="emoji">{l.emoji}</span>
                      {l.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <div className="two-col">
                <label>
                  Subject <em>(optional)</em>
                  <input
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="e.g. Maths, Science, History…"
                  />
                </label>
                <div>
                  <span className="label">Engine</span>
                  <select value={engine} onChange={(e) => setEngine(e.target.value)}>
                    {ENGINES.map((en) => (
                      <option key={en.id} value={en.id}>
                        {en.label} — {en.hint}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <label>
                Anything specific you’re stuck on? <em>(optional)</em>
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. I don't get step 3…"
                />
              </label>

              <div
                className={`drop ${dragOver ? 'over' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(true)
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/*,.pdf"
                  multiple
                  hidden
                  onChange={(e) => {
                    addFiles(e.target.files)
                    e.target.value = ''
                  }}
                />
                <span className="drop-ico">🖼️</span>
                <strong>
                  Add a photo or PDF <span className="opt">(optional)</span>
                </strong>
                <span className="drop-sub">
                  drop it here or click to browse — several pages allowed (max {MAX_FILES})
                </span>
              </div>

              {files.length > 0 && (
                <div className="file-grid">
                  {files.map((f, i) => (
                    <div className="file-card" key={`${f.name}-${i}`}>
                      {previews[i] ? (
                        <img src={previews[i]} alt={f.name} className="thumb" />
                      ) : (
                        <span className="pdf-ico">📄</span>
                      )}
                      <span className="file-name" title={f.name}>
                        {f.name}
                      </span>
                      <button
                        type="button"
                        className="file-remove"
                        onClick={() => removeFile(i)}
                        title="Remove"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {error && <div className="error">⚠️ {error}</div>}

              <button type="submit" className="cta" disabled={loading}>
                {loading ? 'Working it out… (this can take a minute)' : 'Explain it to me'}
              </button>
            </form>
          ) : (
            <section className="panel result">
              <div className="result-head">
                <div className="meta">
                  <span className="badge">{levelLabel(active.level)}</span>
                  {active.subject && <span className="badge">{active.subject}</span>}
                  <span className="badge muted">read via {active.readMethod}</span>
                  <span className="badge muted">engine: {active.engineUsed}</span>
                  {active.fileCount > 1 && (
                    <span className="badge muted">{active.fileCount} pages</span>
                  )}
                </div>
                <div className="actions">
                  <button type="button" className="mini-btn" onClick={copyAnswer}>
                    Copy
                  </button>
                  <button type="button" className="mini-btn" onClick={downloadAnswer}>
                    Download
                  </button>
                  <button type="button" className="mini-btn" onClick={newSession}>
                    New
                  </button>
                </div>
              </div>

              <h2>Here’s how to think about it 👇</h2>
              <Markdown>{active.explanation}</Markdown>

              <details className="extracted">
                <summary>What the app read from your file{active.fileCount > 1 ? 's' : ''}</summary>
                <pre>{active.extractedText}</pre>
              </details>

              <div className="chat">
                <h3>Still stuck? Ask a follow-up</h3>
                {(active.messages || []).map((m, i) => (
                  <div key={i} className={`msg ${m.role}`}>
                    <div className="msg-role">{m.role === 'user' ? 'You' : 'Tutor'}</div>
                    <div className="msg-body">
                      {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
                    </div>
                  </div>
                ))}
                {followupLoading && (
                  <div className="msg assistant">
                    <div className="msg-role">Tutor</div>
                    <div className="msg-body thinking">Thinking…</div>
                  </div>
                )}
                {followupError && <div className="error">⚠️ {followupError}</div>}
                <form className="chat-form" onSubmit={submitFollowup}>
                  <textarea
                    value={followupInput}
                    onChange={(e) => setFollowupInput(e.target.value)}
                    placeholder="e.g. Why did you divide both sides by 2?"
                    rows={2}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        submitFollowup(e)
                      }
                    }}
                  />
                  <button type="submit" className="cta small" disabled={followupLoading}>
                    {followupLoading ? '…' : 'Ask'}
                  </button>
                </form>
              </div>
            </section>
          )}
        </main>
      </div>

      <footer className="foot">
        <span>
          Study Buddy · private local model + optional cloud fallback · your history stays in this
          browser
        </span>
      </footer>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

export default App
