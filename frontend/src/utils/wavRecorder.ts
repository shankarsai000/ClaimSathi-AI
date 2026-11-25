/**
 * In-browser PCM WAV Audio Recorder & Adaptive Noise-Floor VAD for ClaimSathi AI.
 * Captures microphone input via Web Audio API, handles hardware sample rates
 * cleanly by downsampling to 16kHz 16-bit PCM mono WAV for Gnani Prisma STT,
 * suppresses speaker feedback via a silent GainNode, and runs adaptive VAD for
 * Approach C hands-free auto-pause + Layer 0 silence gating.
 */

export type VadState = 'calibrating' | 'listening' | 'speaking' | 'pausing'

export interface WavRecorderVadOptions {
  autoStopOnSilence?: boolean
  speechStartMultiplier?: number
  speechStartOffset?: number
  speechContinueMultiplier?: number
  speechContinueOffset?: number
  calibrationMs?: number
  silenceDurationMs?: number
  minSpeechMs?: number
  maxInitialSilenceMs?: number
  onAutoSilenceStop?: () => void
  onInitialSilenceTimeout?: () => void
  onVadStateChange?: (state: VadState) => void
}

export interface WavRecorderStats {
  hasSpeech: boolean
  peakRms: number
  speechMs: number
  durationMs: number
  noiseFloorRms: number
}

export interface VadFrameResult {
  vadState: VadState
  triggerAutoStop: boolean
  triggerInitialSilenceTimeout: boolean
  normalizedVolume: number
  noiseFloorRms: number
}

export interface AdaptiveVadConfig {
  calibrationMs?: number
  minFloorRms?: number
  maxFloorRms?: number
  speechStartMultiplier?: number
  speechStartOffset?: number
  speechContinueMultiplier?: number
  speechContinueOffset?: number
  silenceDurationMs?: number
  minSpeechMs?: number
  maxInitialSilenceMs?: number
}

/**
 * Pure, DOM-free adaptive Voice Activity Detector using rolling noise-floor estimation
 * and Schmitt-trigger hysteresis so background room/fan noise does not block auto-pause.
 */
export class AdaptiveVadTracker {
  private readonly calibrationMs: number
  private readonly minFloorRms: number
  private readonly maxFloorRms: number
  private readonly speechStartMultiplier: number
  private readonly speechStartOffset: number
  private readonly speechContinueMultiplier: number
  private readonly speechContinueOffset: number
  private readonly silenceDurationMs: number
  private readonly minSpeechMs: number
  private readonly maxInitialSilenceMs: number

  private calibrationSum: number = 0
  private calibrationCount: number = 0
  private noiseFloorRms: number = 0.004
  private peakRms: number = 0
  private totalMs: number = 0
  private speechMs: number = 0
  private hasSpeech: boolean = false
  private activeSpeech: boolean = false
  private lastSpeechAtMs: number = 0
  private autoStopFired: boolean = false
  private initialTimeoutFired: boolean = false

  constructor(config: AdaptiveVadConfig = {}) {
    this.calibrationMs = config.calibrationMs ?? 350
    this.minFloorRms = config.minFloorRms ?? 0.002
    this.maxFloorRms = config.maxFloorRms ?? 0.06
    this.speechStartMultiplier = config.speechStartMultiplier ?? 1.9
    this.speechStartOffset = config.speechStartOffset ?? 0.005
    this.speechContinueMultiplier = config.speechContinueMultiplier ?? 1.4
    this.speechContinueOffset = config.speechContinueOffset ?? 0.0025
    this.silenceDurationMs = config.silenceDurationMs ?? 1500
    this.minSpeechMs = config.minSpeechMs ?? 280
    this.maxInitialSilenceMs = config.maxInitialSilenceMs ?? 12000
  }

  reset(nowMs: number = Date.now()): void {
    this.calibrationSum = 0
    this.calibrationCount = 0
    this.noiseFloorRms = 0.004
    this.peakRms = 0
    this.totalMs = 0
    this.speechMs = 0
    this.hasSpeech = false
    this.activeSpeech = false
    this.lastSpeechAtMs = nowMs
    this.autoStopFired = false
    this.initialTimeoutFired = false
  }

  private clampFloor(floor: number): number {
    return Math.min(this.maxFloorRms, Math.max(this.minFloorRms, floor))
  }

  private getThresholds(): { startThreshold: number; continueThreshold: number } {
    const startThreshold = Math.max(0.0085, this.noiseFloorRms * this.speechStartMultiplier + this.speechStartOffset)
    const continueThreshold = Math.max(0.0055, this.noiseFloorRms * this.speechContinueMultiplier + this.speechContinueOffset)
    return { startThreshold, continueThreshold }
  }

  notifyExternalSpeech(nowMs: number = Date.now()): void {
    this.hasSpeech = true
    this.speechMs = Math.max(this.speechMs, this.minSpeechMs)
    this.lastSpeechAtMs = nowMs
    this.activeSpeech = true
  }

  processFrame(
    rms: number,
    chunkMs: number,
    nowMs: number,
    autoStopEnabled: boolean,
  ): VadFrameResult {
    if (rms > this.peakRms) this.peakRms = rms
    this.totalMs += chunkMs

    if (this.totalMs <= this.calibrationMs) {
      // Do not poison calibration if the speaker starts speaking loudly right away
      const floorSample = rms >= 0.045 ? 0.015 : rms
      this.calibrationSum += floorSample
      this.calibrationCount += 1
      this.noiseFloorRms = this.clampFloor(this.calibrationSum / this.calibrationCount)

      if (rms >= 0.045) {
        this.activeSpeech = true
        this.speechMs += chunkMs
        this.lastSpeechAtMs = nowMs
        if (this.speechMs >= this.minSpeechMs) {
          this.hasSpeech = true
        }
      }

      const vol = Math.min(1.0, Math.max(0, (rms - this.noiseFloorRms * 0.7) * 6.0))
      return {
        vadState: this.hasSpeech ? 'speaking' : 'calibrating',
        triggerAutoStop: false,
        triggerInitialSilenceTimeout: false,
        normalizedVolume: vol,
        noiseFloorRms: this.noiseFloorRms,
      }
    }

    const { startThreshold, continueThreshold } = this.getThresholds()
    const threshold = this.activeSpeech ? continueThreshold : startThreshold

    let triggerAutoStop = false
    let triggerInitialSilenceTimeout = false
    let vadState: VadState = 'listening'

    if (rms >= threshold) {
      this.activeSpeech = true
      this.speechMs += chunkMs
      this.lastSpeechAtMs = nowMs
      if (this.speechMs >= this.minSpeechMs) {
        this.hasSpeech = true
      }
      vadState = 'speaking'
    } else {
      this.activeSpeech = false
      // Slowly track ambient noise floor so steady fan/AC noise adapts cleanly
      this.noiseFloorRms = this.clampFloor(this.noiseFloorRms * 0.94 + rms * 0.06)

      if (this.hasSpeech) {
        const silenceElapsed = nowMs - this.lastSpeechAtMs
        if (silenceElapsed >= 450) {
          vadState = 'pausing'
        }
        if (autoStopEnabled && !this.autoStopFired && silenceElapsed >= this.silenceDurationMs) {
          this.autoStopFired = true
          triggerAutoStop = true
        }
      } else if (
        autoStopEnabled &&
        this.maxInitialSilenceMs > 0 &&
        !this.initialTimeoutFired &&
        this.totalMs >= this.maxInitialSilenceMs
      ) {
        this.initialTimeoutFired = true
        triggerInitialSilenceTimeout = true
      }
    }

    const vol = Math.min(1.0, Math.max(0, (rms - this.noiseFloorRms * 0.7) * 6.0))
    return {
      vadState,
      triggerAutoStop,
      triggerInitialSilenceTimeout,
      normalizedVolume: vol,
      noiseFloorRms: this.noiseFloorRms,
    }
  }

  getStats(): WavRecorderStats {
    return {
      hasSpeech: this.hasSpeech,
      peakRms: this.peakRms,
      speechMs: Math.round(this.speechMs),
      durationMs: Math.round(this.totalMs),
      noiseFloorRms: Number(this.noiseFloorRms.toFixed(5)),
    }
  }
}

/**
 * Downsample mono Float32 PCM buffer cleanly via linear interpolation to match target outputRate (16kHz).
 */
export function downsampleFloat32(
  samples: Float32Array,
  inputRate: number,
  outputRate: number,
): Float32Array {
  if (!samples.length || inputRate <= 0 || outputRate <= 0 || inputRate === outputRate) {
    return samples
  }
  const ratio = inputRate / outputRate
  const outLength = Math.max(1, Math.round(samples.length / ratio))
  const out = new Float32Array(outLength)
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio
    const idx = Math.floor(pos)
    const frac = pos - idx
    const s0 = samples[Math.min(idx, samples.length - 1)]
    const s1 = samples[Math.min(idx + 1, samples.length - 1)]
    out[i] = s0 + (s1 - s0) * frac
  }
  return out
}

export class WavRecorder {
  private audioContext: AudioContext | null = null
  private mediaStream: MediaStream | null = null
  private scriptProcessor: ScriptProcessorNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private muteGainNode: GainNode | null = null
  private recordedChunks: Float32Array[] = []
  private isRecording: boolean = false
  private readonly targetSampleRate: number = 16000
  private actualInputSampleRate: number = 16000
  private onVolumeChange?: (volume: number) => void
  private autoStopOnSilence: boolean = false
  private onAutoSilenceStop?: () => void
  private onInitialSilenceTimeout?: () => void
  private onVadStateChange?: (state: VadState) => void
  private lastEmittedVadState: VadState = 'calibrating'
  private vad: AdaptiveVadTracker

  constructor(
    sampleRate: number = 16000,
    onVolumeChange?: (volume: number) => void,
    options?: WavRecorderVadOptions,
  ) {
    this.targetSampleRate = sampleRate
    this.onVolumeChange = onVolumeChange
    this.autoStopOnSilence = Boolean(options?.autoStopOnSilence)
    this.onAutoSilenceStop = options?.onAutoSilenceStop
    this.onInitialSilenceTimeout = options?.onInitialSilenceTimeout
    this.onVadStateChange = options?.onVadStateChange
    this.vad = new AdaptiveVadTracker({
      calibrationMs: options?.calibrationMs,
      speechStartMultiplier: options?.speechStartMultiplier,
      speechStartOffset: options?.speechStartOffset,
      speechContinueMultiplier: options?.speechContinueMultiplier,
      speechContinueOffset: options?.speechContinueOffset,
      silenceDurationMs: options?.silenceDurationMs ?? 1500,
      minSpeechMs: options?.minSpeechMs ?? 280,
      maxInitialSilenceMs: options?.maxInitialSilenceMs ?? 12000,
    })
  }

  setAutoStopOnSilence(enabled: boolean): void {
    this.autoStopOnSilence = enabled
  }

  notifyExternalSpeechActivity(): void {
    if (!this.isRecording) return
    this.vad.notifyExternalSpeech(Date.now())
    if (this.lastEmittedVadState !== 'speaking') {
      this.lastEmittedVadState = 'speaking'
      this.onVadStateChange?.('speaking')
    }
  }

  getStats(): WavRecorderStats {
    return this.vad.getStats()
  }

  async start(): Promise<void> {
    this.recordedChunks = []
    this.isRecording = true
    this.lastEmittedVadState = 'calibrating'
    this.vad.reset(Date.now())
    this.onVadStateChange?.('calibrating')

    // Request microphone access with acoustic echo cancellation and noise suppression
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: this.targetSampleRate,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })

    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
    this.audioContext = new AudioContextClass({ sampleRate: this.targetSampleRate })
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume()
    }
    this.actualInputSampleRate = this.audioContext.sampleRate || this.targetSampleRate

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream)
    this.scriptProcessor = this.audioContext.createScriptProcessor(2048, 1, 1)

    // Route through a zero-gain node so Chrome clocks onaudioprocess without speaker echo
    this.muteGainNode = this.audioContext.createGain()
    this.muteGainNode.gain.value = 0

    this.scriptProcessor.onaudioprocess = (e: AudioProcessingEvent) => {
      if (!this.isRecording) return

      const inputData = e.inputBuffer.getChannelData(0)
      const chunkCopy = new Float32Array(inputData.length)
      chunkCopy.set(inputData)
      this.recordedChunks.push(chunkCopy)

      let sum = 0
      for (let i = 0; i < inputData.length; i++) {
        sum += inputData[i] * inputData[i]
      }
      const rms = Math.sqrt(sum / inputData.length)
      const chunkMs = (inputData.length / this.actualInputSampleRate) * 1000
      const res = this.vad.processFrame(rms, chunkMs, Date.now(), this.autoStopOnSilence)

      if (this.onVolumeChange) {
        this.onVolumeChange(res.normalizedVolume)
      }

      if (res.vadState !== this.lastEmittedVadState) {
        this.lastEmittedVadState = res.vadState
        this.onVadStateChange?.(res.vadState)
      }

      if (res.triggerAutoStop) {
        setTimeout(() => {
          if (this.isRecording) {
            this.onAutoSilenceStop?.()
          }
        }, 0)
      } else if (res.triggerInitialSilenceTimeout) {
        setTimeout(() => {
          if (this.isRecording) {
            this.onInitialSilenceTimeout?.()
          }
        }, 0)
      }
    }

    this.sourceNode.connect(this.scriptProcessor)
    this.scriptProcessor.connect(this.muteGainNode)
    this.muteGainNode.connect(this.audioContext.destination)
  }

  private cleanupAudioNodes(): void {
    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect()
      } catch {}
      this.sourceNode = null
    }
    if (this.scriptProcessor) {
      this.scriptProcessor.onaudioprocess = null
      try {
        this.scriptProcessor.disconnect()
      } catch {}
      this.scriptProcessor = null
    }
    if (this.muteGainNode) {
      try {
        this.muteGainNode.disconnect()
      } catch {}
      this.muteGainNode = null
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop())
      this.mediaStream = null
    }
  }

  async stop(): Promise<Blob> {
    this.isRecording = false
    this.cleanupAudioNodes()

    if (this.audioContext && this.audioContext.state !== 'closed') {
      await this.audioContext.close()
      this.audioContext = null
    }

    return this.encodeWav()
  }

  cancel(): void {
    this.isRecording = false
    this.cleanupAudioNodes()
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close().catch(() => {})
      this.audioContext = null
    }
    this.recordedChunks = []
  }

  private encodeWav(): Blob {
    let totalLength = 0
    for (const chunk of this.recordedChunks) {
      totalLength += chunk.length
    }

    const mergedRaw = new Float32Array(totalLength)
    let offset = 0
    for (const chunk of this.recordedChunks) {
      mergedRaw.set(chunk, offset)
      offset += chunk.length
    }

    const merged = downsampleFloat32(mergedRaw, this.actualInputSampleRate, this.targetSampleRate)
    const buffer = new ArrayBuffer(44 + merged.length * 2)
    const view = new DataView(buffer)

    this.writeString(view, 0, 'RIFF')
    view.setUint32(4, 36 + merged.length * 2, true)
    this.writeString(view, 8, 'WAVE')

    this.writeString(view, 12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, this.targetSampleRate, true)
    view.setUint32(28, this.targetSampleRate * 2, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)

    this.writeString(view, 36, 'data')
    view.setUint32(40, merged.length * 2, true)

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
