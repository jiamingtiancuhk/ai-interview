# Eval results

Setup: 4 scenarios × 5 simulated personas, up to 14 turns each, seed 0, M5 MacBook (24 GB). The candidate simulator is `qwen3:8b` in every run; only the interviewer changes. Method and metric definitions: [README.md](README.md). Raw per-turn logs are in `results/<run>/turns.jsonl`.

Label-based metrics below count **every** turn, including the ones the label verifier rejected (the conservative variant; verified-only numbers are in each `summary.json`).

## 1. Baseline → improved (same model, same simulator)

| metric | baseline | improved |
|---|---|---|
| Routing accuracy | 82.2% | **95.8%** |
| Vague answers flagged for follow-up | 98.4% | 95.6% |
| Solid answers flagged for follow-up | 99.0% | **0.0%** |
| **Probe discrimination** (vague − solid) | −0.6% | **95.6%** |
| "No more questions" recognised | 0% | **100%** |
| Clarification requests handled | 94.4% | **100%** |
| Candidate questions answered | 72.5% | **100%** |
| …then back to the open question | 79.3% | **100%** |
| Interviews finished within 14 turns | 15% | **95%** |
| Stages within time budget | 89.4% | **100%** |
| Answer → first interviewer sentence, p50 / p95 | 4.4 s / 7.2 s | **3.9 s / 5.5 s** |

What changed, each found by reading the eval's failure cases (`python -m evals.inspect_errors`):

1. **Rubrics never reached the model.** Ollama enforces the JSON schema as a grammar but does not show it to the model, so every field description (scoring anchors, what a field is for) was invisible; the model filled a field called `missing` with the literal word "missing". Structured calls now carry a field guide generated from the schema. This affects routing, profiling, planning, scoring and the report.
2. **No discrimination on follow-ups.** The model flagged 99% of strong answers for a follow-up, so the interviewer drilled into everything and rarely finished. A single 1–5 score was not calibratable for an 8B model either (strong answers 3, vague 4, depending on field order). Routing now answers four yes/no checks (concrete, own actions, numbers, reasoning) and **code** sums them against a threshold.
3. **Loop after candidate questions.** After answering a candidate's question the interviewer re-asked its own, then picked up that bridge sentence as "its question" next time ("back to my question: back to my question: …"), and routing misread the candidate's answer as another question. The open question is now tracked in state, routing judges against it, and consecutive candidate-question turns are capped.
4. **"No more questions" read as a question** (0% correct), so the Q&A stage never ended. A deterministic check (explicit "no more questions", or no interrogative cue at all) overrides that routing.

### Threshold sweep (improved run)

Follow up when the number of passed checks ≤ t:

| t | vague answers followed up | solid answers followed up |
|---|---|---|
| 1 | 56% | 0% |
| **2** (shipped) | **98%** | **0%** |
| 3 | 100% | 2% |
| 4 | 100% | 100% |

## 2. Model choice: qwen3:8b vs qwen3:4b (improved code)

| metric | qwen3:8b | qwen3:4b |
|---|---|---|
| Routing accuracy | **95.8%** | 82.3% |
| Probe discrimination | **95.6%** | 87.1% |
| **Replies leaking the model's reasoning** | **0%** | 83.3% |
| Exactly one question per turn | **100%** | 20.4% |
| Answer → first sentence, p50 | 3.9 s | **2.3 s** |

qwen3:4b is ~40% faster but ignores `think: false` and speaks its chain of thought ("首先，理解角色：我是技术负责人……") in 83% of replies, which would be read aloud to the candidate. qwen3:8b stays the default.

## 3. Ablation: reply guardrails off (same model and prompts)

| metric | guardrails on | off |
|---|---|---|
| Exactly one question per turn | **100%** | 69.6% |
| Replies opening with an echo | **5.3%** | 8.9% |
| Back to the open question after a candidate question | **100%** | 93.3% |
| Clarification requests handled | **100%** | 93.3% |
| Routing accuracy | 95.8% | 97.4% |

Without the code-side guardrails, 30% of the interviewer's turns ask two or three questions at once. Routing is unaffected, as expected: the guardrails only shape the spoken reply.

## Known limitations

- Simulated candidates are an approximation of real ones; the same model family plays candidate and interviewer.
- One seed per configuration; differences of a few points are within noise.
- Remaining weak spots: "I don't know" (75% routed correctly) and off-topic replies (79%).
- The label verifier changed between the baseline and improved runs (it shares the LLM client that gained the field guide), which is why the headline numbers count every turn rather than only verified ones.
