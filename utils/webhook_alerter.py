import requests
import json
import logging
from config import settings

logger = logging.getLogger(__name__)

class WebhookAlerter:
    """
    Real-Time Webhook Alerting Engine for TrendPulse.
    Fires off POST requests to configured endpoints (e.g., Slack, Discord, Zapier)
    when critical events or high-confidence trading signals occur.
    """

    def __init__(self):
        self.endpoints = self._load_endpoints()

    def _load_endpoints(self):
        # In a real scenario, this could load from DB or config.
        # For this implementation, we read from config.py / environment.
        endpoints_str = getattr(settings, 'WEBHOOK_ENDPOINTS', None) or '[]'
        try:
            endpoints = json.loads(endpoints_str)
            if not isinstance(endpoints, list):
                endpoints = []
            return endpoints
        except Exception as e:
            logger.warning(f"Failed to parse WEBHOOK_ENDPOINTS: {e}")
            return []

    def trigger_alert(self, title: str, message: str, level: str = "INFO", data: dict = None):
        """
        Send an alert to all configured webhook endpoints.
        """
        if not self.endpoints:
            logger.debug(f"Webhook Alet triggered but no endpoints configured. Title: {title}")
            return False

        payload = {
            "title": title,
            "message": message,
            "level": level.upper(),
            "source": "TrendPulse AI",
            "data": data or {}
        }

        success_count = 0
        for endpoint in self.endpoints:
            try:
                # Basic POST request (adjust headers as needed per service)
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
                if response.status_code in [200, 201, 202, 204]:
                    success_count += 1
                else:
                    logger.warning(f"Webhook {endpoint} returned status {response.status_code}")
            except Exception as e:
                logger.error(f"Error sending webhook to {endpoint}: {e}")

        return success_count > 0

alerter = WebhookAlerter()
