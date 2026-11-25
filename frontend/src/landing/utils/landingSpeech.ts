import { api } from '../../api'
import { playAudioBlob, stopAudio } from '../../utils/audioPlayer'

const TAG_RE = /<[^<>]{1,32}>/g

export function stripSpeechTags(text: string): string {
  return text.replace(TAG_RE, ' ').replace(/\s+/g, ' ').trim()
}

export function stopLandingSpeech(): void {
  stopAudio()
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
}

/**
 * Speak text on the landing page via Gnani Timbre v3.0 TTS with official emotion tags,
 * cleanly falling back to browser SpeechSynthesis (strictly stripped of <...> tags).
 * Resolves `true` when playback ends naturally, or `false` if interrupted.
 */
export async function speakLandingText(
  speechText: string,
  cleanText: string,
  language: string = 'hi-IN',
  speed: number = 1.0,
): Promise<boolean> {
  stopLandingSpeech()

  try {
    const blob = await api.synthesizeSpeech(speechText || cleanText, {
      language,
      speed,
      demo: false,
    })
    return await playAudioBlob(blob)
  } catch {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return false
    }
    const cleanSpoken = stripSpeechTags(cleanText || speechText)
    if (!cleanSpoken) return false

    return await new Promise<boolean>((resolve) => {
      try {
        window.speechSynthesis.cancel()
        const utt = new SpeechSynthesisUtterance(cleanSpoken)
        utt.lang = language && language !== 'indic-auto' ? language : 'en-IN'
        utt.rate = speed
        utt.onend = () => resolve(true)
        utt.onerror = () => resolve(false)
        window.speechSynthesis.speak(utt)
      } catch {
        resolve(false)
      }
    })
  }
}
