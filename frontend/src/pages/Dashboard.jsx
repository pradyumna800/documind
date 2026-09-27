import { useEffect, useRef, useState } from 'react'
import client from '../api/client'
import { streamAsk } from '../api/streamAsk'
import { useAuth } from '../context/AuthContext'
import StudyPanel from '../components/StudyPanel'
import ProfilePanel from '../components/ProfilePanel'

const UNCATEGORIZED = 'none' // sentinel for "no workspace assigned"

export default function Dashboard() {
  const { logout, user, setUser } = useAuth()

  const [workspaces, setWorkspaces] = useState([])
  const [showHiddenWorkspaces, setShowHiddenWorkspaces] = useState(false)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null) // null = "All documents"
  const [newWorkspaceName, setNewWorkspaceName] = useState('')
  const [showNewWorkspaceInput, setShowNewWorkspaceInput] = useState(false)
  const [editingWorkspaceId, setEditingWorkspaceId] = useState(null)
  const [editingWorkspaceName, setEditingWorkspaceName] = useState('')

  const [documents, setDocuments] = useState([])
  const [selectedDocIds, setSelectedDocIds] = useState([])
  const [uploading, setUploading] = useState(false)
  const [studyDocument, setStudyDocument] = useState(null)
  const [showProfile, setShowProfile] = useState(false)

  const [conversations, setConversations] = useState([])
  const [activeConversation, setActiveConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [compareMode, setCompareMode] = useState(false)

  const [editingConversationId, setEditingConversationId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')

  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    loadConversations()
    loadWorkspaces()
  }, [])

  useEffect(() => {
    loadDocuments()
  }, [activeWorkspaceId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, asking])

  // Comparison mode only makes sense with 2+ documents selected — if the
  // selection drops below that, drop out of compare mode automatically
  // rather than leaving it silently active with nothing to compare.
  useEffect(() => {
    if (selectedDocIds.length < 2) setCompareMode(false)
  }, [selectedDocIds])

  const loadWorkspaces = async () => {
    // Always fetch ALL workspaces (hidden included) — the "show hidden"
    // toggle below only controls what's DISPLAYED, filtered client-side.
    // Fetching only visible ones by default meant the app could never
    // even detect a hidden workspace existed, so the "Show N hidden
    // workspaces" link never appeared and there was no way back.
    const { data } = await client.get('/workspaces/', { params: { include_hidden: 'true' } })
    setWorkspaces(data)
  }

  const loadDocuments = async () => {
    const params = {}
    if (activeWorkspaceId) params.workspace = activeWorkspaceId
    const { data } = await client.get('/documents/', { params })
    setDocuments(data)
  }

  const loadConversations = async () => {
    const { data } = await client.get('/conversations/')
    setConversations(data)
  }

  const createWorkspace = async (e) => {
    e.preventDefault()
    const name = newWorkspaceName.trim()
    if (!name) return
    const { data } = await client.post('/workspaces/', { name })
    setWorkspaces((prev) => [...prev, data].sort((a, b) => a.name.localeCompare(b.name)))
    setNewWorkspaceName('')
    setShowNewWorkspaceInput(false)
    setActiveWorkspaceId(data.id)
  }

  const startRenamingWorkspace = (ws) => {
    setEditingWorkspaceId(ws.id)
    setEditingWorkspaceName(ws.name)
  }

  const saveWorkspaceRename = async (id) => {
    const trimmed = editingWorkspaceName.trim()
    setEditingWorkspaceId(null)
    if (!trimmed) return
    const { data } = await client.patch(`/workspaces/${id}/`, { name: trimmed })
    setWorkspaces((prev) => prev.map((w) => (w.id === id ? data : w)).sort((a, b) => a.name.localeCompare(b.name)))
  }

  const toggleWorkspaceHidden = async (ws) => {
    await client.patch(`/workspaces/${ws.id}/`, { is_hidden: !ws.is_hidden })
    if (!ws.is_hidden && activeWorkspaceId === ws.id) setActiveWorkspaceId(null)
    await loadWorkspaces()
  }

  const deleteWorkspace = async (id) => {
    if (!window.confirm('Delete this workspace? Its documents will move to Uncategorized, not be deleted.')) return
    await client.delete(`/workspaces/${id}/`)
    setWorkspaces((prev) => prev.filter((w) => w.id !== id))
    if (activeWorkspaceId === id) setActiveWorkspaceId(null)
  }

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    const formData = new FormData()
    formData.append('stored_file', file)
    if (activeWorkspaceId && activeWorkspaceId !== UNCATEGORIZED) {
      formData.append('workspace', activeWorkspaceId)
    }
    try {
      await client.post('/documents/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      await loadDocuments()
      await loadWorkspaces()
    } catch (err) {
      alert(err.response?.data?.detail || 'Upload failed.')
    } finally {
      setUploading(false)
      fileInputRef.current.value = ''
    }
  }

  const handleMoveDocument = async (docId, workspaceValue) => {
    await client.patch(`/documents/${docId}/`, { workspace: workspaceValue === UNCATEGORIZED ? null : workspaceValue })
    await loadDocuments()
    await loadWorkspaces()
  }

  const handleDeleteDocument = async (id) => {
    await client.delete(`/documents/${id}/`)
    setSelectedDocIds((prev) => prev.filter((docId) => docId !== id))
    await loadDocuments()
    await loadWorkspaces()
  }

  const toggleDocSelection = (id) => {
    setSelectedDocIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const startNewConversation = async () => {
    const { data } = await client.post('/conversations/', { title: 'New conversation' })
    setConversations((prev) => [data, ...prev])
    setActiveConversation(data)
    setMessages([])
    return data
  }

  const openConversation = async (conversation) => {
    setActiveConversation(conversation)
    const { data } = await client.get(`/conversations/${conversation.id}/messages/`)
    setMessages(data)
  }

  const startRenaming = (conversation) => {
    setEditingConversationId(conversation.id)
    setEditingTitle(conversation.title)
  }

  const saveRename = async (conversationId) => {
    const trimmed = editingTitle.trim()
    setEditingConversationId(null)
    if (!trimmed) return
    const { data } = await client.patch(`/conversations/${conversationId}/`, { title: trimmed })
    setConversations((prev) => prev.map((c) => (c.id === conversationId ? { ...c, title: data.title } : c)))
    setActiveConversation((prev) => (prev?.id === conversationId ? { ...prev, title: data.title } : prev))
  }

  const handleDeleteConversation = async (conversationId) => {
    if (!window.confirm('Delete this conversation? This cannot be undone.')) return
    await client.delete(`/conversations/${conversationId}/`)
    setConversations((prev) => prev.filter((c) => c.id !== conversationId))
    if (activeConversation?.id === conversationId) {
      setActiveConversation(null)
      setMessages([])
    }
  }

  // Updates the LAST message in the list — used while streaming, since the
  // in-progress assistant reply is always the most recent entry.
  const updateLastMessage = (updater) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev
      const updated = [...prev]
      updated[updated.length - 1] = updater(updated[updated.length - 1])
      return updated
    })
  }

  const handleAsk = async (e) => {
    e.preventDefault()
    if (!question.trim() || asking) return
    const convo = activeConversation || (await startNewConversation())
    const askedQuestion = question
    const mode = compareMode ? 'compare' : 'chat'
    setQuestion('')
    setAsking(true)

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: askedQuestion, sources: [] },
      { role: 'assistant', content: '', sources: [], streaming: true },
    ])

    await streamAsk(
      convo.id,
      { question: askedQuestion, documentIds: selectedDocIds, mode },
      {
        onSources: (sources) => updateLastMessage((m) => ({ ...m, sources })),
        onChunk: (text) => updateLastMessage((m) => ({ ...m, content: m.content + text })),
        onDone: async () => {
          updateLastMessage((m) => ({ ...m, streaming: false }))
          setAsking(false)
          await loadConversations()
        },
        onError: (msg) => {
          updateLastMessage((m) => ({
            ...m,
            content: m.content || 'Sorry, something went wrong. Please try again.',
            streaming: false,
          }))
          setAsking(false)
        },
      }
    )
  }

  const activeWorkspaceName =
    activeWorkspaceId === null
      ? 'All documents'
      : activeWorkspaceId === UNCATEGORIZED
      ? 'Uncategorized'
      : workspaces.find((w) => w.id === activeWorkspaceId)?.name || ''

  const visibleWorkspaces = workspaces.filter((w) => showHiddenWorkspaces || !w.is_hidden)
  const hiddenCount = workspaces.filter((w) => w.is_hidden).length
  const initials = (user?.first_name?.[0] || user?.username?.[0] || '?').toUpperCase()

  return (
    <div className="h-screen flex overflow-hidden bg-gray-50 text-gray-900">
      {/* Workspace rail */}
      <aside className="w-56 bg-gray-900 text-gray-100 flex flex-col h-full overflow-hidden shrink-0">
        <div className="p-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-lg">🧠</span>
            <span className="font-semibold tracking-tight">DocuMind</span>
          </div>
        </div>

        <div className="p-3 flex-1 overflow-y-auto min-h-0">
          <div className="flex items-center justify-between px-1 mb-2">
            <h2 className="text-[11px] uppercase tracking-wide text-gray-400 font-semibold">Workspaces</h2>
            <button
              onClick={() => setShowNewWorkspaceInput((v) => !v)}
              className="text-gray-400 hover:text-white text-sm leading-none"
              title="New workspace"
            >
              +
            </button>
          </div>

          {showNewWorkspaceInput && (
            <form onSubmit={createWorkspace} className="mb-2 px-1">
              <input
                autoFocus
                value={newWorkspaceName}
                onChange={(e) => setNewWorkspaceName(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setShowNewWorkspaceInput(false)}
                placeholder="Workspace name..."
                className="w-full text-sm px-2 py-1.5 rounded-md bg-gray-800 border border-gray-700 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-400"
              />
            </form>
          )}

          <button
            onClick={() => setActiveWorkspaceId(null)}
            className={`w-full text-left text-sm px-2 py-1.5 rounded-md mb-0.5 flex items-center gap-2 ${
              activeWorkspaceId === null ? 'bg-indigo-500/20 text-indigo-300' : 'text-gray-300 hover:bg-gray-800'
            }`}
          >
            <span>🗂️</span> All documents
          </button>

          {visibleWorkspaces.map((ws) => (
            <div key={ws.id} className="group flex items-center gap-1 mb-0.5">
              {editingWorkspaceId === ws.id ? (
                <input
                  autoFocus
                  value={editingWorkspaceName}
                  onChange={(e) => setEditingWorkspaceName(e.target.value)}
                  onBlur={() => saveWorkspaceRename(ws.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveWorkspaceRename(ws.id)
                    if (e.key === 'Escape') setEditingWorkspaceId(null)
                  }}
                  className="flex-1 text-sm px-2 py-1 rounded-md bg-gray-800 border border-gray-700"
                />
              ) : (
                <>
                  <button
                    onClick={() => setActiveWorkspaceId(ws.id)}
                    title={ws.name}
                    className={`flex-1 text-left text-sm px-2 py-1.5 rounded-md truncate flex items-center gap-2 ${
                      activeWorkspaceId === ws.id ? 'bg-indigo-500/20 text-indigo-300' : 'text-gray-300 hover:bg-gray-800'
                    } ${ws.is_hidden ? 'opacity-50' : ''}`}
                  >
                    <span>📁</span>
                    <span className="truncate flex-1">
                      {ws.name}
                      {ws.is_hidden && <span className="text-[10px] text-gray-500 ml-1">(hidden)</span>}
                    </span>
                    <span className="text-[11px] text-gray-500">{ws.document_count}</span>
                  </button>
                  <button
                    onClick={() => toggleWorkspaceHidden(ws)}
                    className="opacity-0 group-hover:opacity-100 text-xs text-gray-500 hover:text-gray-200 px-0.5"
                    title={ws.is_hidden ? 'Unhide' : 'Hide'}
                  >
                    {ws.is_hidden ? '🙈' : '👁️'}
                  </button>
                  <button
                    onClick={() => startRenamingWorkspace(ws)}
                    className="opacity-0 group-hover:opacity-100 text-xs text-gray-500 hover:text-gray-200 px-0.5"
                    title="Rename"
                  >
                    ✎
                  </button>
                  <button
                    onClick={() => deleteWorkspace(ws.id)}
                    className="opacity-0 group-hover:opacity-100 text-xs text-gray-500 hover:text-red-400 px-0.5"
                    title="Delete"
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
          ))}

          <button
            onClick={() => setActiveWorkspaceId(UNCATEGORIZED)}
            className={`w-full text-left text-sm px-2 py-1.5 rounded-md mt-1 flex items-center gap-2 ${
              activeWorkspaceId === UNCATEGORIZED ? 'bg-indigo-500/20 text-indigo-300' : 'text-gray-400 hover:bg-gray-800'
            }`}
          >
            <span>📭</span> Uncategorized
          </button>

          {hiddenCount > 0 && (
            <button
              onClick={() => setShowHiddenWorkspaces((v) => !v)}
              className="w-full text-left text-[11px] text-gray-500 hover:text-gray-300 px-2 py-1.5 mt-1"
            >
              {showHiddenWorkspaces ? 'Hide hidden workspaces' : `Show ${hiddenCount} hidden workspace${hiddenCount > 1 ? 's' : ''}`}
            </button>
          )}
        </div>

        <div className="p-3 border-t border-gray-800 shrink-0">
          <button
            onClick={() => setShowProfile(true)}
            className="w-full flex items-center gap-2 px-1 py-1 rounded-md hover:bg-gray-800 text-left"
          >
            <span className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-xs font-semibold shrink-0 overflow-hidden">
              {user?.avatar_url ? <img src={user.avatar_url} alt="" className="w-full h-full object-cover" /> : initials}
            </span>
            <span className="text-sm truncate flex-1">{user?.first_name || user?.username || 'Profile'}</span>
          </button>
          <button onClick={logout} className="text-xs text-gray-400 hover:text-white mt-2 ml-1">Log out</button>
        </div>
      </aside>

      {/* Documents + conversations column */}
      <aside className="w-72 bg-white border-r flex flex-col h-full overflow-hidden shrink-0">
        <div className="p-4 border-b shrink-0">
          <h2 className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">{activeWorkspaceName}</h2>
          <label className="block text-sm bg-indigo-600 text-white rounded-lg px-3 py-2 text-center cursor-pointer hover:bg-indigo-700 transition-colors">
            {uploading ? 'Uploading...' : '+ Upload document'}
            <input ref={fileInputRef} type="file" accept=".pdf,.txt,.docx" className="hidden" onChange={handleUpload} />
          </label>
        </div>

        <div className="p-4 border-b overflow-y-auto max-h-64 shrink-0">
          <ul className="space-y-1.5">
            {documents.map((doc) => (
              <li key={doc.id} className="rounded-lg border border-gray-100 hover:border-gray-200 p-2">
                <div className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={selectedDocIds.includes(doc.id)}
                    onChange={() => toggleDocSelection(doc.id)}
                    className="shrink-0"
                  />
                  <span className="truncate text-sm flex-1" title={doc.original_filename}>{doc.original_filename}</span>
                  {doc.status === 'completed' && (
                    <button onClick={() => setStudyDocument(doc)} title="Study material" className="shrink-0">📚</button>
                  )}
                  <button onClick={() => handleDeleteDocument(doc.id)} className="text-gray-400 hover:text-red-600 shrink-0">✕</button>
                </div>
                <select
                  value={doc.workspace || UNCATEGORIZED}
                  onChange={(e) => handleMoveDocument(doc.id, e.target.value)}
                  className="mt-1 w-full text-[11px] text-gray-500 bg-gray-50 border border-gray-200 rounded px-1.5 py-0.5"
                >
                  <option value={UNCATEGORIZED}>Uncategorized</option>
                  {workspaces.map((ws) => (
                    <option key={ws.id} value={ws.id}>{ws.name}</option>
                  ))}
                </select>
              </li>
            ))}
            {documents.length === 0 && <p className="text-xs text-gray-400">No documents here yet.</p>}
          </ul>

          <div className="flex items-center justify-between mt-2 gap-2">
            <p className="text-xs text-gray-400">
              {selectedDocIds.length > 0 ? `${selectedDocIds.length} selected for chat` : 'None selected = search all your documents'}
            </p>
            {selectedDocIds.length >= 2 && (
              <button
                onClick={() => setCompareMode((v) => !v)}
                title="Structure the answer as an explicit comparison across your selected documents"
                className={`shrink-0 text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                  compareMode
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'text-indigo-600 border-indigo-300 hover:bg-indigo-50'
                }`}
              >
                {compareMode ? '✓ Compare mode' : 'Compare mode'}
              </button>
            )}
          </div>
        </div>

        <div className="p-4 flex-1 overflow-y-auto min-h-0">
          <div className="flex justify-between items-center mb-2">
            <h2 className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Conversations</h2>
            <button onClick={startNewConversation} className="text-xs text-indigo-600 hover:underline">+ New</button>
          </div>
          <ul className="space-y-1">
            {conversations.map((c) => (
              <li key={c.id} className="group flex items-center gap-1">
                {editingConversationId === c.id ? (
                  <input
                    autoFocus
                    className="flex-1 text-sm px-2 py-1 rounded border"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onBlur={() => saveRename(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveRename(c.id)
                      if (e.key === 'Escape') setEditingConversationId(null)
                    }}
                  />
                ) : (
                  <>
                    <button
                      onClick={() => openConversation(c)}
                      title={c.title}
                      className={`flex-1 text-left text-sm px-2 py-1 rounded truncate ${activeConversation?.id === c.id ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-gray-100'}`}
                    >
                      {c.title}
                    </button>
                    <button
                      onClick={() => startRenaming(c)}
                      className="opacity-0 group-hover:opacity-100 text-xs text-gray-400 hover:text-gray-700 px-1"
                      title="Rename"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => handleDeleteConversation(c.id)}
                      className="opacity-0 group-hover:opacity-100 text-xs text-gray-400 hover:text-red-600 px-1"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto min-h-0 p-6 space-y-4">
          {messages.length === 0 && (
            <div className="max-w-md mx-auto mt-16 text-center text-gray-400">
              <div className="text-3xl mb-2">💬</div>
              <p className="text-sm">
                Select or upload documents on the left, then ask a question —
                or click 📚 next to a document for a summary, glossary, and quiz.
                Select 2+ documents to unlock Compare mode.
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`max-w-2xl ${m.role === 'user' ? 'ml-auto text-right' : ''}`}>
              <div className={`inline-block px-4 py-2 rounded-2xl whitespace-pre-wrap ${m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200'}`}>
                {m.role === 'assistant' && m.streaming && m.content === '' ? (
                  <span className="text-gray-400">DocuMind is thinking...</span>
                ) : (
                  <>
                    {m.content}
                    {m.streaming && <span className="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 align-middle animate-pulse" />}
                  </>
                )}
              </div>
              {!m.streaming && m.sources?.length > 0 && (
                <div className="text-xs text-gray-500 mt-1">
                  Sources: {m.sources.map((s, idx) => (
                    <span key={idx}>📄 {s.document_name}{s.page_number ? ` (p.${s.page_number})` : ''}{idx < m.sources.length - 1 ? ', ' : ''}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {compareMode && (
          <div className="bg-indigo-50 text-indigo-700 text-xs px-4 py-1.5 border-t border-indigo-100">
            🔍 Compare mode — answers will explicitly contrast your {selectedDocIds.length} selected documents
          </div>
        )}

        <form onSubmit={handleAsk} className="border-t bg-white p-4 flex gap-2 shrink-0">
          <input
            className="flex-1 border border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
            placeholder={compareMode ? 'Ask me to compare your selected documents...' : 'Ask a question about your documents...'}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl px-5 py-2 transition-colors disabled:opacity-50" disabled={asking}>
            Send
          </button>
        </form>
      </main>

      {studyDocument && (
        <StudyPanel document={studyDocument} onClose={() => setStudyDocument(null)} />
      )}

      {showProfile && user && (
        <ProfilePanel user={user} onClose={() => setShowProfile(false)} onUpdated={setUser} />
      )}
    </div>
  )
}
