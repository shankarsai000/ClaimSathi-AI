/**
 * In-browser PCM WAV Audio Recorder for ClaimSathi AI.
 * Captures microphone input directly as standard 16-bit PCM mono WAV (16kHz).
 * Guarantees direct compatibility with Gnani Prisma STT without requiring WebM conversion.
 */

export class WavRecorder {
  private audioContext: AudioContext | null = null
  private mediaStream: MediaStream | null = null
  private scriptProcessor: ScriptProcessorNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private recordedChunks: Float32Array[] = []
  private isRecording: boolean = false
  private sampleRate: number = 16000
  private onVolumeChange?: (volume: number) => void

  constructor(sampleRate: number = 16000, onVolumeChange?: (volume: number) => void) {
    this.sampleRate = sampleRate
    this.onVolumeChange = onVolumeChange
  }

  async start(): Promise<void> {
    this.recordedChunks = []
    this.isRecording = true

    // Request microphone access
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: this.sampleRate,
        echoCancellation: true,
        noiseSuppression: true,
      },
    })

    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
    this.audioContext = new AudioContextClass({ sampleRate: this.sampleRate })

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream)
    // 4096 buffer size, 1 input channel, 1 output channel
    this.scriptProcessor = this.audioContext.createScriptProcessor(4096, 1, 1)

    this.scriptProcessor.onaudioprocess = (e: AudioProcessingEvent) => {
      if (!this.isRecording) return

      const inputData = e.inputBuffer.getChannelData(0)
      // Copy chunk
      const chunkCopy = new Float32Array(inputData.length)
      chunkCopy.set(inputData)
      this.recordedChunks.push(chunkCopy)

      // Calculate instantaneous volume level for UI feedback
      if (this.onVolumeChange) {
        let sum = 0
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i]
        }
        const rms = Math.sqrt(sum / inputData.length)
        const volume = Math.min(1.0, rms * 4.0) // Scale for visual meter
        this.onVolumeChange(volume)
      }
    }

    this.sourceNode.connect(this.scriptProcessor)
    this.scriptProcessor.connect(this.audioContext.destination)
  }

  async stop(): Promise<Blob> {
    this.isRecording = false

    if (this.scriptProcessor && this.sourceNode) {
      this.sourceNode.disconnect()
      this.scriptProcessor.disconnect()
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop())
      this.mediaStream = null
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      await this.audioContext.close()
      this.audioContext = null
    }

    return this.encodeWav()
  }

  cancel(): void {
    this.isRecording = false
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop())
      this.mediaStream = null
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close()
      this.audioContext = null
    }
    this.recordedChunks = []
  }

  private encodeWav(): Blob {
    // Calculate total sample count
    let totalLength = 0
    for (const chunk of this.recordedChunks) {
      totalLength += chunk.length
    }

    // Merge into single Float32Array
    const merged = new Float32Array(totalLength)
    let offset = 0
    for (const chunk of this.recordedChunks) {
      merged.set(chunk, offset)
      offset += chunk.length
    }

    // Encode to 16-bit PCM WAV container
    const buffer = new ArrayBuffer(44 + merged.length * 2)
    const view = new DataView(buffer)

    // RIFF chunk descriptor
    this.writeString(view, 0, 'RIFF')
    view.setUint32(4, 36 + merged.length * 2, true)
    this.writeString(view, 8, 'WAVE')

    // fmt sub-chunk
    this.writeString(view, 12, 'fmt ')
    view.setUint32(16, 16, true) // SubChunk1Size (16 for PCM)
    view.setUint16(20, 1, true) // AudioFormat (1 for PCM)
    view.setUint16(22, 1, true) // NumChannels (1 mono)
    view.setUint32(24, this.sampleRate, true) // SampleRate
    view.setUint32(28, this.sampleRate * 2, true) // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
    view.setUint16(32, 2, true) // BlockAlign (NumChannels * BitsPerSample/8)
    view.setUint16(34, 16, true) // BitsPerSample (16 bits)

    // data sub-chunk
    this.writeString(view, 36, 'data')
    view.setUint32(40, merged.length * 2, true)

    // Write PCM samples
    let sampleOffset = 44
    for (let i = 0; i < merged.length; i++) {
      const s = Math.max(-1, Math.min(1, merged[i]))
      view.setInt16(sampleOffset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
      sampleOffset += 2
    }

    return new Blob([buffer], { type: 'audio/wav' })
  }

  private writeString(view: DataView, offset: number, string: string): void {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i))
    }
  }
}

