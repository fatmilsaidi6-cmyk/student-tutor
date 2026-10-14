import { getAccessCode } from './storage.js'

function detailMessage(data) {
  const detail = data?.detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  }
  return detail || 'Something went wrong.'
}

function authHeaders() {
  const code = getAccessCode()
  return code ? { 'X-API-Key': code } : {}
}

async function readJson(res) {
  try {
    return await res.json()
  } catch {
    return {}
  }
}

// Wrap fetch so a network-level failure (server down, wrong origin) gives a
// clear message instead of the browser's bare "Failed to fetch".
async function safeFetch(url, options) {
  try {
    return await fetch(url, options)
  } catch {
    throw new Error(
      "Can't reach the server. Make sure the backend is running " +
        '(http://localhost:8000) and that you opened the app from that address.',
    )
  }
}

export async function explainHomework({ text, files, level, subject, question, engine }) {
  const fd = new FormData()
  fd.append('text', text || '')
  for (const f of files) fd.append('files', f)
  fd.append('level', level)
  fd.append('subject', subject)
  fd.append('question', question)
  fd.append('engine', engine)

  const res = await safeFetch('/api/explain', {
    method: 'POST',
    headers: authHeaders(),
    body: fd,
  })
  const data = await readJson(res)
  if (!res.ok) throw new Error(detailMessage(data))
  return data
}

export async function askFollowup({ context, messages, level, subject, engine }) {
  const res = await safeFetch('/api/followup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ context, messages, level, subject, engine }),
  })
  const data = await readJson(res)
  if (!res.ok) throw new Error(detailMessage(data))
  return data
}
