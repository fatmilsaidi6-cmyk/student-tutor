import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

// The AI often writes LaTeX with \( \) and \[ \] delimiters, which
// remark-math doesn't understand. Normalise them to $ / $$ first.
function normalizeMath(text) {
  if (!text) return ''
  return text
    .replace(/\\\[/g, () => '\n$$\n')
    .replace(/\\\]/g, () => '\n$$\n')
    .replace(/\\\(/g, () => '$')
    .replace(/\\\)/g, () => '$')
}

export default function Markdown({ children }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  )
}
