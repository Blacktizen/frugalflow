The file `ratelimit.log` contains one request per line in the form `epoch_seconds user`, for example `1700000000 alice`. A rate limit allows at most 5 requests per user in any rolling 60 second window, where the window for a request at time `t` is the interval `(t-60, t]`, so a request exactly 60 seconds earlier is outside the window. When a request arrives, it is refused if that user already has 5 accepted requests inside that window; refused requests do not count toward the window for later requests. The file is not sorted by time. Write `limited.json` as a JSON object mapping each user to the number of their requests that were refused.

For example, if the file contained only `100 alice`, `110 alice`, `120 alice`, `130 alice`, `140 alice` and `150 alice`, then `alice` would have 1 refused request (the one at 150).

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
