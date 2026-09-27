# Recorded inference scorecard

Real Gemma 4 12B / vLLM 0.30.0 / H100 capture. Percentiles use completed requests and nearest rank. Mean ITL percentiles describe request averages, not individual token intervals. See [method and setup](../inference-metrics.md).

## baseline

8 completed / 8 attempted; 0 missing final usage. Observed wall time: 26.109636 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 8 | 0.193175 | 0.282202 | 0.282202 | 0.282202 |
| Client request duration (seconds) | 8 | 3.218366 | 3.547286 | 3.547286 | 3.547286 |
| Native engine TTFT (seconds) | 8 | 0.056401 | 0.062358 | 0.062358 | 0.062358 |
| Native queue wait (seconds) | 8 | 0.000049 | 0.000053 | 0.000053 | 0.000053 |
| Native prefill (seconds) | 8 | 0.049104 | 0.057483 | 0.057483 | 0.057483 |
| Native decode (seconds) | 8 | 2.988646 | 3.261796 | 3.261796 | 3.261796 |
| Per-request mean ITL (seconds) | 8 | 0.023533 | 0.025683 | 0.025683 | 0.025683 |
| Per-request engine output tokens/s (tokens/s) | 8 | 41.942324 | 43.265937 | 43.265937 | 43.265937 |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 0.306400 |
| completed requests per second | 0.306400 |
| completed input tokens per second | 14.094413 |
| completed output tokens per second | 39.219237 |

Completed-request tokens: 368 input; 1,024 output.

## queue-pressure

32 completed / 32 attempted; 0 missing final usage. Observed wall time: 62.594338 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 32 | 22.435854 | 25.681270 | 25.681393 | 25.693712 |
| Client request duration (seconds) | 32 | 29.349791 | 33.194015 | 33.238286 | 33.239749 |
| Native engine TTFT (seconds) | 32 | 22.225912 | 25.484476 | 25.516745 | 25.516901 |
| Native queue wait (seconds) | 32 | 22.147980 | 25.334722 | 25.378793 | 25.378797 |
| Native prefill (seconds) | 32 | 0.058117 | 0.069479 | 0.076483 | 0.096243 |
| Native decode (seconds) | 32 | 7.588128 | 10.602450 | 10.605189 | 10.605189 |
| Per-request mean ITL (seconds) | 32 | 0.029757 | 0.041578 | 0.041589 | 0.041589 |
| Per-request engine output tokens/s (tokens/s) | 32 | 32.602377 | 41.550973 | 41.733239 | 41.733239 |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 0.511228 |
| completed requests per second | 0.511228 |
| completed input tokens per second | 24.890430 |
| completed output tokens per second | 130.874457 |

Completed-request tokens: 1,558 input; 8,192 output.

## long-context

8 completed / 8 attempted; 0 missing final usage. Observed wall time: 18.811119 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 8 | 0.660216 | 3.977245 | 3.977245 | 3.977245 |
| Client request duration (seconds) | 8 | 3.963756 | 7.106560 | 7.106560 | 7.106560 |
| Native engine TTFT (seconds) | 8 | 0.456598 | 3.858449 | 3.858449 | 3.858449 |
| Native queue wait (seconds) | 8 | 0.000016 | 0.000056 | 0.000056 | 0.000056 |
| Native prefill (seconds) | 8 | 0.272454 | 3.444381 | 3.444381 | 3.444381 |
| Native decode (seconds) | 8 | 3.238455 | 3.486912 | 3.486912 | 3.486912 |
| Per-request mean ITL (seconds) | 8 | 0.025500 | 0.027456 | 0.027456 | 0.027456 |
| Per-request engine output tokens/s (tokens/s) | 8 | 34.618514 | 38.353934 | 38.353934 | 38.353934 |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 0.425280 |
| completed requests per second | 0.425280 |
| completed input tokens per second | 2734.978165 |
| completed output tokens per second | 54.435889 |

Completed-request tokens: 51,448 input; 1,024 output.

## recovery

8 completed / 8 attempted; 0 missing final usage. Observed wall time: 26.028843 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 8 | 0.188900 | 0.254392 | 0.254392 | 0.254392 |
| Client request duration (seconds) | 8 | 3.222264 | 3.465168 | 3.465168 | 3.465168 |
| Native engine TTFT (seconds) | 8 | 0.055249 | 0.062102 | 0.062102 | 0.062102 |
| Native queue wait (seconds) | 8 | 0.000041 | 0.000058 | 0.000058 | 0.000058 |
| Native prefill (seconds) | 8 | 0.047928 | 0.052715 | 0.052715 | 0.052715 |
| Native decode (seconds) | 8 | 3.002321 | 3.190738 | 3.190738 | 3.190738 |
| Per-request mean ITL (seconds) | 8 | 0.023640 | 0.025124 | 0.025124 | 0.025124 |
| Per-request engine output tokens/s (tokens/s) | 8 | 41.773716 | 43.333540 | 43.333540 | 43.333540 |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 0.307351 |
| completed requests per second | 0.307351 |
| completed input tokens per second | 14.138162 |
| completed output tokens per second | 39.340973 |

Completed-request tokens: 368 input; 1,024 output.

## invalid-request

0 completed / 1 attempted; 1 missing final usage. Observed wall time: 0.110461 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Client request duration (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native engine TTFT (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native queue wait (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native prefill (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native decode (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Per-request mean ITL (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Per-request engine output tokens/s (tokens/s) | 0 | unavailable | unavailable | unavailable | unavailable |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 9.052975 |
| completed requests per second | 0.000000 |
| completed input tokens per second | 0.000000 |
| completed output tokens per second | 0.000000 |

Completed-request tokens: 0 input; 0 output.

## client-early-close

0 completed / 4 attempted; 4 missing final usage. Observed wall time: 0.633440 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Client request duration (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native engine TTFT (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native queue wait (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native prefill (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Native decode (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Per-request mean ITL (seconds) | 0 | unavailable | unavailable | unavailable | unavailable |
| Per-request engine output tokens/s (tokens/s) | 0 | unavailable | unavailable | unavailable | unavailable |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 6.314726 |
| completed requests per second | 0.000000 |
| completed input tokens per second | 0.000000 |
| completed output tokens per second | 0.000000 |

Completed-request tokens: 0 input; 0 output.

## all

56 completed / 61 attempted; 5 missing final usage. Observed wall time: 137.526791 s.

| Metric | n | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Client first-content latency (seconds) | 56 | 3.977245 | 23.535628 | 25.681291 | 25.693712 |
| Client request duration (seconds) | 56 | 10.897797 | 31.362424 | 33.221120 | 33.239749 |
| Native engine TTFT (seconds) | 56 | 3.858449 | 23.361086 | 25.516592 | 25.516901 |
| Native queue wait (seconds) | 56 | 0.000070 | 23.279719 | 25.378789 | 25.378797 |
| Native prefill (seconds) | 56 | 0.057483 | 0.254892 | 0.273454 | 3.444381 |
| Native decode (seconds) | 56 | 6.108001 | 7.888326 | 10.605189 | 10.605189 |
| Per-request mean ITL (seconds) | 56 | 0.026609 | 0.030935 | 0.041589 | 0.041589 |
| Per-request engine output tokens/s (tokens/s) | 56 | 34.776295 | 42.102841 | 42.938047 | 43.333540 |

| Whole-scenario rate | Value |
|---|---:|
| attempted requests per second | 0.443550 |
| completed requests per second | 0.407193 |
| completed input tokens per second | 390.774769 |
| completed output tokens per second | 81.904042 |

Completed-request tokens: 53,742 input; 11,264 output.
