"""
app/integrations/utils.py

Common utilities for integration clients including:
- IntegrationError exception type
- Retry decorators with exponential backoff
- In-process rate limiters for free-tier constraints
"""

import asyncio
import logging
from functools import wraps
import time

logger = logging.getLogger(__name__)

class IntegrationError(Exception):
    """Raised when an external integration fails, indicating a fallback should be used."""
    pass

def retry_with_backoff(max_retries: int = 2, base_delay: float = 1.0, max_delay: float = 5.0):
    """
    Decorator for retrying async functions with exponential backoff.
    Fails fast for 4xx errors (if the exception indicates it).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            delay = base_delay
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Fail fast for 4xx HTTP errors if it's an httpx exception
                    if hasattr(e, "response") and e.response is not None:
                        if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                            logger.error(f"[{func.__name__}] Failing fast on 4xx error: {e.response.status_code}")
                            raise IntegrationError(f"Client error {e.response.status_code}: {e}")
                    
                    # For Twilio 4xx errors (20000+ codes are usually client config)
                    if hasattr(e, "status") and e.status and 400 <= e.status < 500:
                        logger.error(f"[{func.__name__}] Failing fast on client error: {e.status}")
                        raise IntegrationError(f"Client error: {e}")

                    if retries >= max_retries:
                        logger.error(f"[{func.__name__}] Max retries ({max_retries}) reached. Failing.")
                        raise IntegrationError(f"Max retries reached: {e}")
                        
                    retries += 1
                    logger.warning(f"[{func.__name__}] Transient error, retrying {retries}/{max_retries} in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, max_delay)
        return wrapper
    return decorator

class RateLimiter:
    """
    Simple in-process token bucket rate limiter to respect free-tier API limits.
    """
    def __init__(self, calls: int, period: float):
        self.calls = calls
        self.period = period
        self.timestamps = []
        self._lock = asyncio.Lock()
        
    async def acquire(self):
        async with self._lock:
            now = time.time()
            # Remove timestamps older than the period
            self.timestamps = [t for t in self.timestamps if now - t < self.period]
            
            if len(self.timestamps) >= self.calls:
                sleep_time = self.period - (now - self.timestamps[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached. Sleeping for {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    # After sleeping, update now
                    now = time.time()
                    self.timestamps = [t for t in self.timestamps if now - t < self.period]
            
            self.timestamps.append(now)
