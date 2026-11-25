/**
 * Audio playback helper for Gnani Timbre synthesized speech.
 * Resolves `true` when playback finishes naturally, or `false` if interrupted/stopped.
 */

let currentAudio: HTMLAudioElement | null = null
let currentResolve: ((completed: boolean) => void) | null = null
let currentUrl: string | null = null

export function playAudioBlob(blob: Blob): Promise<boolean> {
  return new Promise((resolve, reject) => {
    stopAudio()
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }

    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    currentResolve = resolve
    currentUrl = url

    audio.onended = () => {
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      currentAudio = null
      currentResolve = null
      currentUrl = null
      resolve(true)
    }

    audio.onerror = () => {
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      currentAudio = null
      currentResolve = null
      currentUrl = null
      reject(new Error('Audio playback failed'))
    }

    audio.play().catch((err) => {
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      currentAudio = null
      currentResolve = null
      currentUrl = null
      reject(err)
    })
  })
}

export function stopAudio(): void {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.currentTime = 0
    currentAudio = null
  }
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = null
  }
  if (currentResolve) {
    const res = currentResolve
    currentResolve = null
    res(false)
  }
}
