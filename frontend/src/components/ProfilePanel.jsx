import { useState, useRef } from 'react'
import client from '../api/client'

/**
 * Slide-in profile panel: view/edit name, bio, and avatar. Mirrors the
 * StudyPanel's slide-in pattern so the app has one consistent "detail
 * panel" interaction instead of introducing a whole new UI pattern.
 */
export default function ProfilePanel({ user, onClose, onUpdated }) {
  const [firstName, setFirstName] = useState(user.first_name || '')
  const [lastName, setLastName] = useState(user.last_name || '')
  const [bio, setBio] = useState(user.bio || '')
  const [avatarPreview, setAvatarPreview] = useState(user.avatar_url || null)
  const [avatarFile, setAvatarFile] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  const initials = (firstName?.[0] || user.username[0] || '?').toUpperCase()

  const handleAvatarChange = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setAvatarFile(file)
    setAvatarPreview(URL.createObjectURL(file))
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('first_name', firstName)
      formData.append('last_name', lastName)
      formData.append('bio', bio)
      if (avatarFile) formData.append('avatar', avatarFile)

      const { data } = await client.patch('/auth/me/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onUpdated(data)
      onClose()
    } catch (err) {
      setError('Could not save your profile. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex justify-end z-50" onClick={onClose}>
      <div
        className="bg-white w-full max-w-md h-full overflow-y-auto p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-6">
          <h2 className="text-lg font-semibold">Your profile</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">✕</button>
        </div>

        <form onSubmit={handleSave} className="space-y-5">
          <div className="flex flex-col items-center gap-3">
            <button
              type="button"
              onClick={() => fileInputRef.current.click()}
              className="w-20 h-20 rounded-full overflow-hidden bg-indigo-600 text-white flex items-center justify-center text-2xl font-semibold hover:opacity-90 transition-opacity"
              title="Change photo"
            >
              {avatarPreview ? (
                <img src={avatarPreview} alt="Avatar" className="w-full h-full object-cover" />
              ) : (
                initials
              )}
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
            <button type="button" onClick={() => fileInputRef.current.click()} className="text-xs text-indigo-600 hover:underline">
              Change photo
            </button>
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-gray-500 font-semibold mb-1">Username</label>
            <p className="text-sm text-gray-700 px-3 py-2 bg-gray-50 rounded-lg">{user.username}</p>
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-gray-500 font-semibold mb-1">Email</label>
            <p className="text-sm text-gray-700 px-3 py-2 bg-gray-50 rounded-lg">{user.email || '—'}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs uppercase tracking-wide text-gray-500 font-semibold mb-1">First name</label>
              <input
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wide text-gray-500 font-semibold mb-1">Last name</label>
              <input
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-gray-500 font-semibold mb-1">Bio</label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              maxLength={200}
              rows={3}
              placeholder="A short line about yourself..."
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
            />
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg py-2 text-sm font-medium disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save changes'}
          </button>
        </form>
      </div>
    </div>
  )
}
