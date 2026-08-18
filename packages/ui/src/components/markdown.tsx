'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Renders freeform AI-generated markdown (e.g. streamed prose responses) as
// compact, product-styled sections instead of a raw pre-wrap text dump —
// matches the app's small-font, tight-spacing design language.
export function Markdown({ content }: { content: string }) {
  return (
    <div className="space-y-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-5 first:mt-0 mb-2 pb-1.5 border-b border-slate-100">
              {children}
            </h2>
          ),
          h2: ({ children }) => (
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-5 first:mt-0 mb-2 pb-1.5 border-b border-slate-100">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-slate-800 mt-4 mb-1.5">{children}</h3>
          ),
          p: ({ children }) => (
            <p className="text-sm text-slate-600 leading-relaxed mb-3">{children}</p>
          ),
          strong: ({ children }) => <strong className="font-semibold text-slate-800">{children}</strong>,
          ul: ({ children }) => (
            <ul className="space-y-1.5 mb-3 pl-4 list-disc marker:text-indigo-300">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="space-y-1.5 mb-3 pl-4 list-decimal marker:text-indigo-400 marker:font-semibold">{children}</ol>
          ),
          li: ({ children }) => <li className="text-sm text-slate-600 leading-relaxed">{children}</li>,
          hr: () => <hr className="border-slate-100 my-4" />,
          code: ({ children }) => (
            <code className="bg-slate-100 px-1.5 py-0.5 rounded-md text-xs font-mono text-slate-700">{children}</code>
          ),
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto mb-3 rounded-xl border border-slate-100">
              <table className="w-full text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
          th: ({ children }) => (
            <th className="text-left px-3 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {children}
            </th>
          ),
          td: ({ children }) => <td className="px-3 py-2 text-sm text-slate-600 border-t border-slate-100">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
