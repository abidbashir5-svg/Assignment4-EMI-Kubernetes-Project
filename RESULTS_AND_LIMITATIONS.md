# Results and limitations

## Fixed replicas
- Fifteen requested replica/rate combinations are recorded.
- Raw reports and summary CSVs are retained under the results directory.
- At higher target request rates, achieved rate fell below target and client/HTTP errors increased.
- Mean response time must be read alongside successful reply counts; failed requests do not contribute a normal response-time sample.

## Graph 2
- Three EMI web pods were sampled at two timestamps.
- CPU request: 100m per pod.
- CPU: 5m, 4m, 4m at both samples (5%, 4%, 4% of requests).
- Memory: 29Mi, 32Mi, 34Mi.
- `httperf` achieved 48.5 req/s in the targeted capture, not the nominal 100 req/s. A later `kubectl top` sample failed.

## HPA
The earlier archived time-series has 19 of 40 expected 15-second observations, ending at 4m45s. The final repeated run's aggregate screenshot reported:
- Offered 33,003
- Submitted/completed 9,091
- Dropped 23,912
- HTTP 2xx 6,198
- HTTP 5xx 2,084
- Other/client errors 809

The latest repeat-run time-series CSV was not present in the archive. Its aggregate result is therefore stored separately and not merged with the earlier time-series.
