FROM redis:7-alpine

# Bind to all interfaces so the Fly internal network can reach us, and
# require a password (set via REDIS_PASSWORD secret at deploy time).
# `--save ""` disables RDB snapshots — we only use Redis as a cache + Celery
# broker, both of which are recoverable from scratch (prewarm sweep refills
# all cache keys in ~5 min, Celery tasks are idempotent), so disk I/O for
# persistence is pure overhead. `--appendonly no` keeps AOF off for the
# same reason.
CMD ["sh", "-c", "exec redis-server --bind 0.0.0.0 :: --protected-mode no --port 6379 --save '' --appendonly no --requirepass \"$REDIS_PASSWORD\" --maxmemory 200mb --maxmemory-policy allkeys-lru"]
