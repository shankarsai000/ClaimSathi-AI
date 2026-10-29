import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import type { ClaimRecord, TimelineEvent } from '../types'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import DemoBadge from '../components/DemoBadge'
import { playAudioBlob, stopAudio } from '../utils/audioPlayer'
import {
  ArrowLeft,
  MapPin,
  Calendar,
  Car,
  FileText,
  Hash,
  AlertCircle,
  Clock,
  Volume2,
  VolumeX,
} from 'lucide-react'

const fieldConfig = [
  { key: 'policy_reference', label: 'Policy Reference', icon: Hash },
  { key: 'incident_location', label: 'Incident Location', icon: MapPin },
  { key: 'incident_date', label: 'Incident Date', icon: Calendar },
  { key: 'vehicle_type', label: 'Vehicle Type', icon: Car },
  { key: 'damage_description', label: 'Damage Description', icon: FileText },
] as const

export default function ClaimDetail() {
  const { id } = useParams<{ id: string }>()
  const [claim, setClaim] = useState<ClaimRecord | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)
  const [isSynthesizing, setIsSynthesizing] = useState(false)

  useEffect(() => {
    if (!id) return
    api.getClaim(id)
      .then((data) => {
        setClaim(data.claim)
        setTimeline(data.timeline)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))

    return () => {
      stopAudio()
    }
  }, [id])

  const handlePlayTranscript = async () => {
    if (isPlayingAudio) {
      stopAudio()
      setIsPlayingAudio(false)
      return
    }

    if (!claim?.transcript) return

    setIsSynthesizing(true)
    try {
      const audioBlob = await api.synthesizeSpeech(claim.transcript, {
        language: 'hi-IN',
        voice: 'Nalini',
      })
      setIsSynthesizing(false)
      setIsPlayingAudio(true)

      await playAudioBlob(audioBlob)
      setIsPlayingAudio(false)
    } catch (err: any) {
      setIsSynthesizing(false)
      setIsPlayingAudio(false)
      alert(`TTS synthesis error: ${err.message}`)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error || !claim) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          <AlertCircle className="w-5 h-5 shrink-0" /> {error || 'Claim not found.'}
        </div>
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-sm text-blue-600 mt-4 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-blue-600 mb-4 hover:underline"
      >
        <ArrowLeft className="w-4 h-4" /> Dashboard
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{claim.id}</h1>
        <StatusBadge status={claim.status} />
        <DemoBadge />
      </div>

      {/* Claim details card */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6 shadow-sm">
        <h2 className="font-semibold text-gray-900 mb-4">Claim Details</h2>
        <dl className="grid sm:grid-cols-2 gap-4">
          {fieldConfig.map(({ key, label, icon: Icon }) => (
            <div
              key={key}
              className="flex items-start gap-3 bg-gray-50 rounded-xl px-4 py-3 border border-gray-100"
            >
              <Icon className="w-5 h-5 text-blue-600 mt-0.5 shrink-0" />
              <div>
                <dt className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {label}
                </dt>
                <dd className="text-sm font-medium text-gray-800 mt-0.5 capitalize">
                  {(claim as any)[key]}
                </dd>
              </div>
            </div>
          ))}
        </dl>
      </div>

      {/* Transcript with TTS */}
      {claim.transcript && (
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-5 mb-6 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">
              Recorded Transcript
            </h2>
            <button
              type="button"
              onClick={handlePlayTranscript}
              disabled={isSynthesizing}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-300 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors shadow-sm disabled:opacity-50"
            >
              {isSynthesizing ? (
                <>
                  <Spinner size="sm" /> Synthesizing...
                </>
              ) : isPlayingAudio ? (
                <>
                  <VolumeX className="w-3.5 h-3.5 text-red-600" /> Stop
                </>
              ) : (
                <>
                  <Volume2 className="w-3.5 h-3.5 text-blue-600" /> Listen (Timbre TTS)
                </>
              )}
            </button>
          </div>
          <p className="text-sm text-gray-700 italic leading-relaxed bg-white p-3.5 rounded-xl border border-gray-200 font-serif">
            "{claim.transcript}"
          </p>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-600" /> Activity Timeline
        </h2>
        {timeline.length === 0 ? (
          <p className="text-sm text-gray-400">No events recorded.</p>
        ) : (
          <ol className="relative border-l-2 border-gray-200 ml-3 space-y-6">
            {timeline.map((evt, i) => (
              <li key={i} className="ml-6">
                <span className="absolute -left-[9px] w-4 h-4 rounded-full bg-blue-600 border-2 border-white" />
                <time className="text-xs text-gray-400">
                  {new Date(evt.timestamp).toLocaleString()}
                </time>
                <h3 className="text-sm font-semibold text-gray-800">{evt.title}</h3>
                <p className="text-sm text-gray-500">{evt.description}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}
