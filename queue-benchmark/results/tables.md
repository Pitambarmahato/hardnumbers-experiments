
### Throughput (jobs/s, median; min-max in brackets)

| Config | Enqueue (10 in flight) | Drain, 1 worker | Drain, 4 workers | Drain, 16 workers |
|---|---|---|---|---|
| postgres | 25027 (20680-25835) | 2751 (2507-2817) | 6623 (6052-6843) | 7943 (7535-8088) |
| postgres-nosync | 35699 (35697-39443) | 4001 (3859-4054) | 10767 (10434-10796) | 7181 (6928-7391) |
| redis | 50597 (48860-51726) | 8189 (8156-11093) | 25807 (25353-26088) | 32159 (31779-32572) |
| redis-aof | 44052 (41360-44168) | 7705 (6863-8003) | 19277 (12219-23109) | 27706 (22902-28471) |
| rabbitmq-default | 28124 (24371-29336) | 9067 (8382-9101) | 19986 (17503-20046) | 42296 (20804-49187) |
| rabbitmq-persistent | 17998 (12207-21410) | 9197 (8537-9286) | 20868 (18881-22023) | 55455 (44569-72157) |
| nats | 27766 (27140-28226) | 11203 (11023-11258) | 31087 (30311-31216) | 88181 (59909-91009) |

### End-to-end latency at 1000 jobs/s, 4 workers (ms, median of repeats)

| Config | p50 | p95 | p99 | max | Jobs skipped (overload) |
|---|---|---|---|---|---|
| postgres | 10.8 | 16.7 | 19.9 | 190 | 0 |
| postgres-nosync | 9.9 | 16.2 | 19.9 | 104 | 0 |
| redis | 8.7 | 14.2 | 16.0 | 58 | 0 |
| redis-aof | 8.5 | 14.3 | 97.9 | 225 | 0 |
| rabbitmq-default | 8.4 | 16.2 | 75.6 | 185 | 0 |
| rabbitmq-persistent | 8.3 | 13.3 | 37.4 | 154 | 0 |
| nats | 7.9 | 12.7 | 14.4 | 52 | 0 |

### SIGKILL the broker 5 s into a 2000 jobs/s producer

| Config | Confirmed | Survived | Lost | Lost % | Processed but not confirmed | Duplicates | Runs |
|---|---|---|---|---|---|---|---|
| postgres | 10227 | 10227 | 0 (0-0) | 0.0% | 0 | 0 | 3 |
| postgres-nosync | 10202 | 10200 | 2 (2-6) | 0.0% | 0 | 0 | 3 |
| redis | 10119 | 0 | 10119 (10092-10155) | 100.0% | 0 | 0 | 3 |
| redis-aof | 10193 | 10193 | 0 (0-0) | 0.0% | 0 | 0 | 3 |
| rabbitmq-default | 10192 | 0 | 10192 (10071-10271) | 100.0% | 0 | 0 | 3 |
| rabbitmq-persistent | 10203 | 10203 | 0 (0-0) | 0.0% | 0 | 0 | 3 |
| nats | 10202 | 10202 | 0 (0-0) | 0.0% | 0 | 0 | 3 |

### Resources at peak (the driver is one single-threaded Node process, so ~90-100% means the driver, not the broker, is the ceiling)

| Config | Broker CPU % | Driver CPU % | Broker MiB |
|---|---|---|---|
| postgres | 214 | 64 | 161 |
| postgres-nosync | 211 | 55 | 164 |
| redis | 52 | 86 | 93 |
| redis-aof | 108 | 95 | 94 |
| rabbitmq-default | 177 | 34 | 223 |
| rabbitmq-persistent | 114 | 50 | 232 |
| nats | 65 | 59 | 46 |
