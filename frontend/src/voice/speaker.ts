import type { Language } from '../api'

const LOCALE: Record<Language, string> = { zh: 'zh-CN', en: 'en-US' }
// Split after sentence-ending punctuation so speech starts before the LLM finishes.
const SENTENCE_END = /[。！？!?；;\n]|[.](?=\s)/

// macOS also ships novelty voices ("Bubbles", "Bad News"...) and robotic
// Eloquence voices ("Eddy", "Flo"...) under the same locales; never use those.
const UNSUITABLE =
  /^(Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Good News|Jester|Organ|Superstar|Trinoids|Whisper|Wobble|Zarvox|Fred|Junior|Kathy|Ralph|Eddy|Flo|Grandma|Grandpa|Reed|Rocko|Sandy|Shelley)\b/i
const PREFERRED = /^(Samantha|Ava|Allison|Susan|Tom|Alex|Evan|Nathan|Zoe|Tingting|婷婷|Lili|莉莉|Yu-shu|语舒)\b/i

function pickVoice(lang: Language): SpeechSynthesisVoice | undefined {
  const voices = speechSynthesis
    .getVoices()
    .filter((v) => v.lang.replace('_', '-').startsWith(LOCALE[lang]) && !UNSUITABLE.test(v.name))
  // "Premium"/"Enhanced" variants sound far better when the user has installed them.
  const rank = (v: SpeechSynthesisVoice) =>
    (/premium|高级/i.test(v.name) ? 8 : 0) +
    (/enhanced|增强/i.test(v.name) ? 4 : 0) +
    (PREFERRED.test(v.name) ? 2 : 0) +
    (v.default ? 1 : 0)
  return voices.sort((a, b) => rank(b) - rank(a))[0]
}

/** Streams interviewer text into the OS speech synthesizer, one sentence at a time. */
export class Speaker {
  private buffer = ''
  private pending = 0
  private generation = 0 // bumped by cancel() so stale onend events are ignored
  private flushed = true
  // Chrome can garbage-collect queued utterances and never fire onend; hold references.
  private live = new Set<SpeechSynthesisUtterance>()
  private voice?: SpeechSynthesisVoice
  onIdle: () => void = () => {}
  onStart: () => void = () => {}
  enabled = true
  private readonly lang: Language

  constructor(lang: Language) {
    this.lang = lang
    this.voice = pickVoice(lang)
    // Chrome loads voices asynchronously.
    speechSynthesis.onvoiceschanged = () => {
      this.voice = pickVoice(lang)
    }
  }

  get speaking() {
    return this.pending > 0
  }

  feed(text: string) {
    this.flushed = false
    this.buffer += text
    for (;;) {
      const m = SENTENCE_END.exec(this.buffer)
      if (!m) break
      const cut = m.index + m[0].length
      this.say(this.buffer.slice(0, cut))
      this.buffer = this.buffer.slice(cut)
    }
  }

  /** Call when the interviewer's turn is complete. */
  flush() {
    this.say(this.buffer)
    this.buffer = ''
    this.flushed = true
    if (this.pending === 0) this.onIdle()
  }

  replay(text: string) {
    this.cancel()
    this.feed(text)
    this.flush()
  }

  cancel() {
    this.buffer = ''
    this.pending = 0
    this.flushed = true
    this.generation++
    this.live.clear()
    speechSynthesis.cancel()
  }

  private say(text: string) {
    const t = text.trim()
    if (!t || !this.enabled) return
    const u = new SpeechSynthesisUtterance(t)
    u.lang = LOCALE[this.lang]
    if (this.voice) u.voice = this.voice
    u.rate = this.lang === 'zh' ? 1.05 : 1.0
    if (this.pending === 0) this.onStart()
    this.pending++
    const gen = this.generation
    this.live.add(u)
    const done = () => {
      this.live.delete(u)
      if (gen !== this.generation) return
      this.pending = Math.max(0, this.pending - 1)
      if (this.pending === 0 && this.flushed) this.onIdle()
    }
    u.onend = done
    u.onerror = done
    speechSynthesis.speak(u)
  }
}
