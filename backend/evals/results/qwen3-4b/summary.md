# Eval: qwen3-4b

| metric | value |
|---|---|
| name | qwen3-4b |
| interviewer_model | qwen3:4b |
| candidate_model | qwen3:8b |
| guardrails | True |
| seed | 0 |
| wall_time_s | 2143 |
| turns | 203 |
| simulator_fidelity | 0.739 |
| routing_accuracy | 0.827 |
| vague_probe_recall | 1.0 |
| vague_follow_up_rate | 0.864 |
| solid_probe_rate | 0.077 |
| probe_discrimination | 0.923 |
| clarify_handled | 0.867 |
| candidate_question_answered | 1.0 |
| candidate_question_returns_to_topic | 0.125 |
| one_question_rate | 0.204 |
| echo_rate | 0.0 |
| empty_reply_rate | 0.0 |
| reasoning_leak_rate | 0.833 |
| route_latency_p50 | 1.42 |
| route_latency_p95 | 1.96 |
| first_sentence_p50 | 2.26 |
| first_sentence_p95 | 4.14 |
| threshold_sweep | [{'threshold': 1, 'vague': 0.833, 'solid': 0.077, 'gap': 0.756}, {'threshold': 2, 'vague': 1.0, 'solid': 0.077, 'gap': 0.923}, {'threshold': 3, 'vague': 1.0, 'solid': 0.096, 'gap': 0.904}, {'threshold': 4, 'vague': 1.0, 'solid': 1.0, 'gap': 0.0}] |
| interviews | 20 |
| finished_rate | 0.95 |
| reached_candidate_questions | 0.95 |
| stages_within_budget | 0.924 |
| stage_time_ratio_median | 0.55 |
| total_time_ratio_median | 0.59 |

Routing accuracy by behavior:

- candidate_question: 1.0
- clarify: 0.867
- dont_know: 0.444
- no_more_questions: 0.857
- off_topic: 0.333
- solid: 0.904
- vague: 0.8

Follow-up threshold sweep (follow up when specificity <= t):

| t | vague followed up | solid followed up | gap |
|---|---|---|---|
| 1 | 0.833 | 0.077 | 0.756 |
| 2 | 1.0 | 0.077 | 0.923 |
| 3 | 1.0 | 0.096 | 0.904 |
| 4 | 1.0 | 1.0 | 0.0 |
