# Eval: no-guardrails

| metric | value |
|---|---|
| name | no-guardrails |
| interviewer_model | qwen3:8b |
| candidate_model | qwen3:8b |
| guardrails | False |
| seed | 0 |
| wall_time_s | 1898 |
| turns | 190 |
| simulator_fidelity | 0.937 |
| routing_accuracy | 0.972 |
| vague_probe_recall | 0.976 |
| vague_follow_up_rate | 0.968 |
| solid_probe_rate | 0.0 |
| probe_discrimination | 0.976 |
| clarify_handled | 0.933 |
| candidate_question_answered | 1.0 |
| candidate_question_returns_to_topic | 0.933 |
| one_question_rate | 0.696 |
| echo_rate | 0.089 |
| empty_reply_rate | 0.0 |
| reasoning_leak_rate | 0.0 |
| route_latency_p50 | 2.49 |
| route_latency_p95 | 3.11 |
| first_sentence_p50 | 3.83 |
| first_sentence_p95 | 5.86 |
| threshold_sweep | [{'threshold': 1, 'vague': 0.524, 'solid': 0.0, 'gap': 0.524}, {'threshold': 2, 'vague': 0.976, 'solid': 0.0, 'gap': 0.976}, {'threshold': 3, 'vague': 1.0, 'solid': 0.019, 'gap': 0.981}, {'threshold': 4, 'vague': 1.0, 'solid': 1.0, 'gap': 0.0}] |
| interviews | 20 |
| finished_rate | 0.95 |
| reached_candidate_questions | 1.0 |
| stages_within_budget | 0.989 |
| stage_time_ratio_median | 0.43 |
| total_time_ratio_median | 0.35 |

Routing accuracy by behavior:

- candidate_question: 1.0
- clarify: 0.933
- dont_know: 0.714
- no_more_questions: 1.0
- off_topic: 0.857
- solid: 1.0
- vague: 0.976

Follow-up threshold sweep (follow up when specificity <= t):

| t | vague followed up | solid followed up | gap |
|---|---|---|---|
| 1 | 0.524 | 0.0 | 0.524 |
| 2 | 0.976 | 0.0 | 0.976 |
| 3 | 1.0 | 0.019 | 0.981 |
| 4 | 1.0 | 1.0 | 0.0 |
