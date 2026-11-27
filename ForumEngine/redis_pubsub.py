import redis
import json
import os
from loguru import logger
import threading

try:
    from config import settings
except ImportError:
    settings = None

class RedisEventBus:
    def __init__(self):
        if settings is not None:
            self.host = getattr(settings, 'REDIS_HOST', 'redis')
            self.port = int(getattr(settings, 'REDIS_PORT', 6379))
        else:
            self.host = os.getenv('REDIS_HOST', 'redis')
            self.port = int(os.getenv('REDIS_PORT', 6379))
        self.client = redis.Redis(host=self.host, port=self.port, db=0)
        self.pubsub = self.client.pubsub()
        self.callbacks = {}
        self.listener_thread = None
        self._running = False

    def publish(self, channel: str, message: dict):
        try:
            self.client.publish(channel, json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")

    def subscribe(self, channel: str, callback):
        self.callbacks[channel] = callback
        self.pubsub.subscribe(channel)
        if not self._running:
            self._start_listening()

    def _start_listening(self):
        self._running = True
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()

    def _listen(self):
        import time, threading
        while self._running:
            try:
                for message in self.pubsub.listen():
                    if message['type'] == 'message':
                        channel = message['channel'].decode('utf-8')
                        data = json.loads(message['data'].decode('utf-8'))
                        if channel in self.callbacks:
                            try:
                                self.callbacks[channel](data)
                            except Exception as e:
                                logger.error(f"Error in Redis callback for {channel}: {e}")
            except Exception as e:
                logger.error(f"Redis PubSub connection error: {e}. Reconnecting in 5 seconds...")
                threading.Event().wait(5)
                try:
                    # Attempt to re-establish the connection
                    self.client.ping()
                    # Resubscribe to all channels
                    for channel in self.callbacks:
                        self.pubsub.subscribe(channel)
                except Exception as reconnect_e:
                    logger.error(f"Redis reconnect failed: {reconnect_e}")
    def stop(self):
        self._running = False
        if self.pubsub:
            self.pubsub.close()
        if self.client:
            self.client.close()

# Singleton instance
event_bus = RedisEventBus()
