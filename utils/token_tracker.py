import redis
import json
import logging
from config import settings as config

logger = logging.getLogger(__name__)

class TokenTracker:
    def __init__(self):
        self.redis_client = None
        self._init_redis()

    def _init_redis(self):
        try:
            redis_host = getattr(config, 'REDIS_HOST', None) or 'localhost'
            redis_port = int(getattr(config, 'REDIS_PORT', None) or 6379)
            redis_db = int(getattr(config, 'REDIS_DB', None) or 0)
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True
            )
            self.redis_client.ping()
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for token tracking: {e}")
            self.redis_client = None

    def log_usage(self, agent_name: str, model_name: str, prompt_tokens: int, completion_tokens: int):
        if not self.redis_client:
            return

        try:
            # Simple cost estimation (can be expanded based on model)
            # Default to GPT-4o pricing roughly: $2.50 / 1M input, $10.00 / 1M output
            prompt_cost_per_token = 2.50 / 1000000
            completion_cost_per_token = 10.00 / 1000000

            cost = (prompt_tokens * prompt_cost_per_token) + (completion_tokens * completion_cost_per_token)

            data = {
                "agent_name": agent_name,
                "model_name": model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost": cost
            }

            pipe = self.redis_client.pipeline()
            # Store in a list
            pipe.lpush("trendpulse:token_usage", json.dumps(data))
            # Keep only the last 1000 records
            pipe.ltrim("trendpulse:token_usage", 0, 999)

            # Also update aggregates
            pipe.hincrby("trendpulse:token_stats", "total_prompt_tokens", prompt_tokens)
            pipe.hincrby("trendpulse:token_stats", "total_completion_tokens", completion_tokens)
            pipe.hincrbyfloat("trendpulse:token_stats", "total_estimated_cost", cost)
            pipe.execute()

        except Exception as e:
            logger.error(f"Error logging token usage: {e}")

    def get_stats(self):
        if not self.redis_client:
            return {"error": "Redis not connected"}

        try:
            # ⚡ PERFORMANCE OPTIMIZATION: Batches separate hgetall and lrange network requests into a single atomic Redis pipeline transaction. Reduces latency by roughly ~50% per invocation by halving network roundtrips.
            pipe = self.redis_client.pipeline()
            pipe.hgetall("trendpulse:token_stats")
            pipe.lrange("trendpulse:token_usage", 0, 99)
            stats, recent = pipe.execute()

            return {
                "aggregate": {
                    "total_prompt_tokens": int(stats.get("total_prompt_tokens", 0)),
                    "total_completion_tokens": int(stats.get("total_completion_tokens", 0)),
                    "total_estimated_cost": float(stats.get("total_estimated_cost", 0.0))
                },
                "recent_usage": [json.loads(x) for x in recent]
            }
        except Exception as e:
            logger.error(f"Error retrieving token stats: {e}")
            return {"error": str(e)}

tracker = TokenTracker()
