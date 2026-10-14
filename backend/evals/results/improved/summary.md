# Eval: improved

| metric | value |
|---|---|
| name | improved |
| interviewer_model | qwen3:8b |
| candidate_model | qwen3:8b |
| guardrails | True |
| seed | 0 |
| wall_time_s | 1866 |
| turns | 189 |
| simulator_fidelity | 0.91 |
| routing_accuracy | 0.971 |
| vague_probe_recall | 0.976 |
| vague_follow_up_rate | 1.0 |
| solid_probe_rate | 0.0 |
| probe_discrimination | 0.976 |
| clarify_handled | 1.0 |
| candidate_question_answered | 1.0 |
| candidate_question_returns_to_topic | 1.0 |
| one_question_rate | 1.0 |
| echo_rate | 0.053 |
| empty_reply_rate | 0.0 |
| reasoning_leak_rate | 0.0 |
| route_latency_p50 | 2.51 |
| route_latency_p95 | 2.97 |
| first_sentence_p50 | 3.85 |
| first_sentence_p95 | 5.5 |
| threshold_sweep | [{'threshold': 1, 'vague': 0.561, 'solid': 0.0, 'gap': 0.561}, {'threshold': 2, 'vague': 0.976, 'solid': 0.0, 'gap': 0.976}, {'threshold': 3, 'vague': 1.0, 'solid': 0.019, 'gap': 0.981}, {'threshold': 4, 'vague': 1.0, 'solid': 1.0, 'gap': 0.0}] |
| interviews | 20 |
| finished_rate | 0.95 |
| reached_candidate_questions | 0.95 |
| stages_within_budget | 1.0 |
| stage_time_ratio_median | 0.42 |
| total_time_ratio_median | 0.35 |

Routing accuracy by behavior:

- candidate_question: 1.0
- clarify: 1.0
- dont_know: 0.75
- no_more_questions: 1.0
- off_topic: 1.0
- solid: 1.0
- vague: 0.927

Follow-up threshold sweep (follow up when specificity <= t):

| t | vague followed up | solid followed up | gap |
|---|---|---|---|
| 1 | 0.561 | 0.0 | 0.561 |
| 2 | 0.976 | 0.0 | 0.976 |
| 3 | 1.0 | 0.019 | 0.981 |
| 4 | 1.0 | 1.0 | 0.0 |
