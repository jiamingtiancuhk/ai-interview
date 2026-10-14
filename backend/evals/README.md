# Interviewer evals

Automated, reproducible evaluation of the interviewer's behaviour: does it follow up on weak answers, leave strong ones alone, handle clarifications and the candidate's own questions, ask one question at a time, and keep to the schedule?

## Method

**Simulated candidates with ground truth.** A persona (`strong`, `vague`, `mixed`, `confused`, `curious`) defines a seeded schedule of behaviours, one per turn: `solid`, `vague`, `off_topic`, `clarify`, `dont_know`, `candidate_question` (and in the Q&A stage, `no_more_questions`). The *harness* decides the behaviour; a candidate model only acts it out. Each turn therefore carries a known label, so routing and policy decisions can be scored without an LLM judge.

**Verified labels.** A second call checks that the simulated reply really shows the intended behaviour; mismatches are regenerated up to twice, and turns that still fail are excluded from label-based metrics. Simulator fidelity is reported with every run.

**Real engine, virtual clock.** Interviews run through the production `InterviewSession` (planning, routing, policy, streamed reply with guardrails). Time advances by estimated speaking time, so stage budgets are exercised without waiting for real minutes.

**Fixed comparison setup.** 4 scenarios (backend and data analyst in Chinese, frontend and PM in English; different interviewer roles and styles) × 5 personas, up to 14 turns each, seed 0. The candidate model stays `qwen3:8b` when the interviewer model changes.

## Metrics

| metric | meaning |
|---|---|
| routing_accuracy | routed answer type equals the intended one |
| vague_probe_recall | vague answers flagged for a follow-up |
| solid_probe_rate | solid answers flagged for a follow-up (not always wrong; the gap matters) |
| probe_discrimination | vague_probe_recall − solid_probe_rate |
| vague_follow_up_rate | vague answers actually followed up when the policy allowed it |
| clarify_handled | clarification requests answered by rephrasing |
| candidate_question_answered / returns_to_topic | the candidate's questions are answered, then the interviewer returns to its open question |
| one_question_rate | replies that ask exactly one question |
| echo_rate | replies opening by restating the previous message |
| stages_within_budget | stages finishing within 1.25× their time budget |
| latency p50/p95 | routing call; answer submitted → interviewer's first sentence |

## Usage

```bash
uv run python -m evals.run --name baseline            # ~45 min on an M5
uv run python -m evals.run --model qwen3:4b --name qwen3-4b
uv run python -m evals.run --no-guardrails --name no-guardrails
uv run python -m evals.compare baseline improved qwen3-4b
uv run python -m evals.inspect_errors baseline       # confusion matrix + failure examples
```

## Results

See [RESULTS.md](RESULTS.md).
