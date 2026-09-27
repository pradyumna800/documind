import { useState, useEffect } from 'react'
import client from '../api/client'

/**
 * A slide-in panel showing a document's auto-generated study material:
 * summary, key-terms glossary, and an interactive quiz. This is the core
 * of DocuMind's "study companion" identity — it's generated proactively
 * per document rather than requiring the user to keep asking questions.
 */
export default function StudyPanel({ document, onClose }) {
  const [insights, setInsights] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [quizAnswers, setQuizAnswers] = useState({}) // { questionIndex: selectedOptionIndex }
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    client.get(`/documents/${document.id}/insights/`).then(({ data }) => {
      if (cancelled) return
      if (data.status === 'completed') setInsights(data)
      setLoaded(true)
    })
    return () => { cancelled = true }
  }, [document.id])

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await client.post(`/documents/${document.id}/insights/`)
      setInsights(data)
      setQuizAnswers({})
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not generate study material. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const selectAnswer = (questionIndex, optionIndex) => {
    setQuizAnswers((prev) => ({ ...prev, [questionIndex]: optionIndex }))
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex justify-end z-50" onClick={onClose}>
      <div
        className="bg-white w-full max-w-lg h-full overflow-y-auto p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-lg font-semibold">📚 Study material</h2>
            <p className="text-sm text-gray-500 truncate max-w-xs" title={document.original_filename}>
              {document.original_filename}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">✕</button>
        </div>

        {!loaded && <p className="text-sm text-gray-400">Loading...</p>}

        {loaded && !insights && (
          <div className="text-center py-10">
            <p className="text-sm text-gray-500 mb-4">
              No study material yet. Generate a summary, key terms, and a quiz from this document.
            </p>
            <button
              onClick={generate}
              disabled={loading}
              className="bg-black text-white rounded-lg px-4 py-2 text-sm disabled:opacity-50"
            >
              {loading ? 'Generating... this can take several minutes on a local model' : 'Generate study material'}
            </button>
            {loading && (
              <p className="text-xs text-gray-400 mt-3">
                Please keep this tab open and wait — no need to click again.
              </p>
            )}
            {error && <p className="text-red-600 text-sm mt-3">{error}</p>}
          </div>
        )}

        {insights && (
          <div className="space-y-8">
            <div className="text-right">
              <button onClick={generate} disabled={loading} className="text-xs text-gray-400 underline disabled:opacity-50">
                {loading ? 'Regenerating... this can take a while' : 'Regenerate'}
              </button>
            </div>

            <section>
              <h3 className="text-sm font-semibold uppercase text-gray-500 mb-2">Summary</h3>
              <p className="text-sm leading-relaxed">{insights.summary}</p>
            </section>

            <section>
              <h3 className="text-sm font-semibold uppercase text-gray-500 mb-2">Key terms</h3>
              <dl className="space-y-3">
                {insights.key_terms?.map((kt, i) => (
                  <div key={i}>
                    <dt className="font-medium text-sm">{kt.term}</dt>
                    <dd className="text-sm text-gray-600">{kt.definition}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section>
              <h3 className="text-sm font-semibold uppercase text-gray-500 mb-3">Quiz</h3>
              <div className="space-y-5">
                {insights.quiz?.map((q, qi) => {
                  const selected = quizAnswers[qi]
                  const answered = selected !== undefined
                  return (
                    <div key={qi} className="border rounded-lg p-3">
                      <p className="text-sm font-medium mb-2">{qi + 1}. {q.question}</p>
                      <div className="space-y-1">
                        {q.options?.map((opt, oi) => {
                          const isCorrect = oi === q.correct_index
                          const isSelected = oi === selected
                          let style = 'border-gray-200'
                          if (answered && isSelected && isCorrect) style = 'border-green-500 bg-green-50'
                          else if (answered && isSelected && !isCorrect) style = 'border-red-500 bg-red-50'
                          else if (answered && isCorrect) style = 'border-green-500'
                          return (
                            <button
                              key={oi}
                              disabled={answered}
                              onClick={() => selectAnswer(qi, oi)}
                              className={`w-full text-left text-sm border rounded px-2 py-1.5 ${style} ${!answered ? 'hover:bg-gray-50' : ''}`}
                            >
                              {opt}
                            </button>
                          )
                        })}
                      </div>
                      {answered && (
                        <p className="text-xs text-gray-500 mt-2">
                          {selected === q.correct_index ? '✅ Correct. ' : '❌ Not quite. '}
                          {q.explanation}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
