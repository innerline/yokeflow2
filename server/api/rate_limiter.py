"""
Simple Rate Limiting for YokeFlow API
======================================

Provides basic rate limiting to prevent abuse and ensure system stability.
Uses in-memory storage for simplicity (can be upgraded to Redis later).
"""

import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
import asyncio


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.

    This is suitable for single-instance deployments. For multi-instance
    deployments, consider using Redis-based rate limiting.
    """

    def __init__(self):
        # Store request timestamps per key (IP or user ID)
        self.requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        # Lock for thread-safe operations
        self.lock = asyncio.Lock()

        # Default limits (can be customized per endpoint)
        self.default_limits = {
            "per_minute": 60,
            "per_hour": 600,
            "per_day": 5000,
        }

        # Endpoint-specific limits
        self.endpoint_limits = {
            # Critical endpoints have stricter limits
            "/api/projects": {
                "per_minute": 5,
                "per_hour": 20,
                "per_day": 100,
            },
            "/api/auth/login": {
                "per_minute": 5,
                "per_hour": 20,
                "per_day": 100,
            },
            # Health check can be called more frequently
            "/api/health": {
                "per_minute": 120,
                "per_hour": 3600,
                "per_day": 50000,
            },
        }

    async def check_rate_limit(
        self,
        key: str,
        endpoint: Optional[str] = None,
        custom_limits: Optional[Dict[str, int]] = None,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if a request is within rate limits.

        Args:
            key: Unique identifier (IP address or user ID)
            endpoint: API endpoint path (for endpoint-specific limits)
            custom_limits: Optional custom limits to override defaults

        Returns:
            Tuple of (allowed, retry_after_seconds)
            - allowed: True if within limits, False otherwise
            - retry_after_seconds: How long to wait before retrying (if limited)
        """
        async with self.lock:
            now = time.time()

            # Clean old requests
            self._clean_old_requests(key, now)

            # Get applicable limits
            limits = self._get_limits(endpoint, custom_limits)

            # Check each time window
            for window_name, limit in limits.items():
                window_seconds = self._get_window_seconds(window_name)
                window_start = now - window_seconds

                # Count requests in this window
                request_count = sum(
                    1 for timestamp in self.requests[key] if timestamp > window_start
                )

                if request_count >= limit:
                    # Calculate when the oldest request in window expires
                    oldest_in_window = min(
                        (t for t in self.requests[key] if t > window_start),
                        default=window_start,
                    )
                    retry_after = int(window_seconds - (now - oldest_in_window)) + 1

                    return False, retry_after

            # Request is allowed - record it
            self.requests[key].append(now)
            return True, None

    def _clean_old_requests(self, key: str, now: float) -> None:
        """Remove requests older than 24 hours."""
        day_ago = now - 86400  # 24 hours in seconds

        # Filter out old requests
        self.requests[key] = deque(
            (t for t in self.requests[key] if t > day_ago),
            maxlen=1000,
        )

    def _get_limits(
        self,
        endpoint: Optional[str] = None,
        custom_limits: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """Get applicable rate limits for the request."""
        if custom_limits:
            return custom_limits

        # Check for endpoint-specific limits
        if endpoint:
            # Try exact match first
            if endpoint in self.endpoint_limits:
                return self.endpoint_limits[endpoint]

            # Try prefix match for parameterized endpoints
            for pattern, limits in self.endpoint_limits.items():
                if endpoint.startswith(pattern):
                    return limits

        return self.default_limits

    def _get_window_seconds(self, window_name: str) -> int:
        """Convert window name to seconds."""
        windows = {
            "per_minute": 60,
            "per_hour": 3600,
            "per_day": 86400,
        }
        return windows.get(window_name, 60)

    def get_client_key(self, request: Request, user_id: Optional[str] = None) -> str:
        """
        Get rate limiting key for a request.

        Args:
            request: FastAPI request object
            user_id: Optional authenticated user ID

        Returns:
            Rate limiting key (user ID if authenticated, otherwise IP)
        """
        # Prefer user ID for authenticated users
        if user_id:
            return f"user:{user_id}"

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"

        # Check for proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip

        return f"ip:{client_ip}"

    async def rate_limit_endpoint(
        self,
        request: Request,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Check rate limit for an endpoint and raise exception if exceeded.

        Args:
            request: FastAPI request object
            endpoint: Override endpoint path (uses request.url.path if not provided)
            user_id: Optional authenticated user ID

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded
        """
        key = self.get_client_key(request, user_id)
        endpoint_path = endpoint or str(request.url.path)

        allowed, retry_after = await self.check_rate_limit(key, endpoint_path)

        if not allowed:
            headers = {"Retry-After": str(retry_after)} if retry_after else {}

            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                headers=headers,
            )


# Global rate limiter instance
rate_limiter = RateLimiter()


# FastAPI dependency for rate limiting
async def check_rate_limit(request: Request) -> None:
    """
    FastAPI dependency to check rate limits.

    Usage:
        @app.get("/api/endpoint", dependencies=[Depends(check_rate_limit)])
        async def endpoint():
            ...
    """
    await rate_limiter.rate_limit_endpoint(request)


# Decorator for custom rate limits
def rate_limit(per_minute: int = 60, per_hour: int = 600, per_day: int = 5000):
    """
    Decorator to apply custom rate limits to an endpoint.

    Usage:
        @app.get("/api/endpoint")
        @rate_limit(per_minute=10, per_hour=100)
        async def endpoint(request: Request):
            ...
    """

    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            custom_limits = {
                "per_minute": per_minute,
                "per_hour": per_hour,
                "per_day": per_day,
            }

            key = rate_limiter.get_client_key(request)
            allowed, retry_after = await rate_limiter.check_rate_limit(
                key, str(request.url.path), custom_limits
            )

            if not allowed:
                headers = {"Retry-After": str(retry_after)} if retry_after else {}
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                    headers=headers,
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator