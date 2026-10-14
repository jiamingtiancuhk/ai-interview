import { MicVAD } from '@ricky0123/vad-web'
import { useCallback, useEffect, useRef, useState } from 'react'

interface Callbacks {
  /** A finished speech segment: 16 kHz mono float32 PCM. */
  onSegment: (audio: Float32Array) => void
  onSpeechStart?: () => void
}

/**
 * Microphone with Silero voice-activity detection running in the browser.
 * Emits one PCM segment per utterance; pauses longer than `redemptionMs`
 * split segments (the caller decides when the whole answer is done).
 */
export function useMic(cb: Callbacks) {
  const vad = useRef<MicVAD | null>(null)
  const cbRef = useRef(cb)
  cbRef.current = cb
  const [state, setState] = useState<'off' | 'loading' | 'ready' | 'error'>('off')
  const [error, setError] = useState('')
  const [listening, setListening] = useState(false)
  const [userSpeaking, setUserSpeaking] = useState(false)

  const init = useCallback(async () => {
    if (vad.current) return vad.current
    setState('loading')
    try {
      vad.current = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        startOnLoad: false,
        positiveSpeechThreshold: 0.5,
        negativeSpeechThreshold: 0.35,
        redemptionMs: 900,
        preSpeechPadMs: 300,
        minSpeechMs: 300,
        getStream: () =>
          navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          }),
        onSpeechStart: () => {
          setUserSpeaking(true)
          cbRef.current.onSpeechStart?.()
        },
        onVADMisfire: () => setUserSpeaking(false),
        onSpeechEnd: (audio) => {
          setUserSpeaking(false)
          cbRef.current.onSegment(audio)
        },
      })
      setState('ready')
      return vad.current
    } catch (e) {
      setState('error')
      setError((e as Error).message || String(e))
      return null
    }
  }, [])

  const start = useCallback(async () => {
    const v = await init()
    if (!v) return
    await v.start()
    setListening(true)
  }, [init])

  const pause = useCallback(async () => {
    setListening(false)
    setUserSpeaking(false)
    await vad.current?.pause()
  }, [])

  useEffect(
    () => () => {
      vad.current?.destroy()
      vad.current = null
    },
    [],
  )

  return { state, error, listening, userSpeaking, init, start, pause }
}
