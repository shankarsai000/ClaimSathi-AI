/**
 * Audio playback helper for Gnani Timbre synthesized speech.
 */

let currentAudio: HTMLAudioElement | null = null

export function playAudioBlob(blob: Blob): Promise<void> {
  return new Promise((resolve, reject) => {
    // Stop any existing playback
    stopAudio()

    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio

    audio.onended = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      resolve()
    }

    audio.onerror = (e) => {
      URL.revokeObjectURL(url)
      currentAudio = null
      reject(new Error('Audio playback failed'))
    }

    audio.play().catch((err) => {
      URL.revokeObjectURL(url)
      currentAudio = null
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
}

