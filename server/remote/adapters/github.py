"""
GitHub Platform Adapter
=======================

Adapter for GitHub Webhooks and API.

Features:
- Webhook event handling (issues, pull requests, comments)
- GitHub API integration
- Signature verification for security
"""

import hashlib
import hmac
import os
from datetime import datetime
from typing import Any, Optional, Callable, Awaitable

import httpx

from server.remote.adapters.base import (
    IPlatformAdapter,
    PlatformMessage,
    MessageType,
    SendResult,
)
from server.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubAdapter(IPlatformAdapter):
    """
    GitHub webhook and API adapter.

    This adapter receives events via webhooks and can send responses
    through the GitHub API (issues, comments, etc.).

    Requirements:
    - GitHub App or Personal Access Token
    - Webhook secret for signature verification
    - Repository access
    """

    API_BASE = "https://api.github.com"

    def __init__(
        self,
        token: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        message_handler: Optional[Callable[[PlatformMessage], Awaitable[None]]] = None,
    ):
        """
        Initialize the GitHub adapter.

        Args:
            token: GitHub Personal Access Token or App token.
                   Falls back to GITHUB_TOKEN env var.
            webhook_secret: Secret for verifying webhook signatures.
                           Falls back to GITHUB_WEBHOOK_SECRET env var.
            message_handler: Async callback for received events
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.webhook_secret = webhook_secret or os.getenv("GITHUB_WEBHOOK_SECRET")
        self.message_handler = message_handler

        self._client: Optional[httpx.AsyncClient] = None
        self._running = False

        if not self.token:
            logger.warning("remote.github.no_token")

    @property
    def platform_name(self) -> str:
        return "github"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "YokeFlow-Remote-Control",
            }
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE,
                headers=headers,
                timeout=30.0
            )
        return self._client

    async def start(self) -> None:
        """
        Start the GitHub adapter.

        Note: GitHub uses webhooks, so there's no polling to start.
        This method just verifies credentials and marks as running.
        """
        if self._running:
            logger.warning("remote.github.already_running")
            return

        if not self.token:
            raise ValueError("GitHub token is required")

        # Verify token is valid
        client = await self._get_client()
        try:
            response = await client.get("/user")
            if response.status_code == 200:
                user = response.json()
                logger.info(
                    "remote.github.started",
                    user=user.get("login")
                )
            else:
                # Token might be a GitHub App token, try /app endpoint
                response = await client.get("/app")
                if response.status_code == 200:
                    app = response.json()
                    logger.info(
                        "remote.github.app_started",
                        app_name=app.get("name")
                    )
                else:
                    logger.warning("remote.github.token_unverified")
        except Exception as e:
            logger.warning("remote.github.verify_failed", error=str(e))

        self._running = True

    async def stop(self) -> None:
        """Stop the adapter and clean up resources."""
        self._running = False

        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

        logger.info("remote.github.stopped")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the X-Hub-Signature-256 header from GitHub.

        Args:
            payload: Raw request body bytes
            signature: Value of X-Hub-Signature-256 header

        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.warning("remote.github.no_webhook_secret")
            return True  # Skip verification if no secret configured

        if not signature.startswith("sha256="):
            return False

        expected = signature[7:]  # Remove "sha256=" prefix

        # Compute HMAC-SHA256
        mac = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        )
        computed = mac.hexdigest()

        return hmac.compare_digest(computed, expected)

    async def handle_webhook(
        self,
        event_type: str,
        payload: dict,
        raw_payload: bytes,
        signature: str
    ) -> bool:
        """
        Handle an incoming webhook from GitHub.

        Args:
            event_type: X-GitHub-Event header value
            payload: Parsed JSON payload
            raw_payload: Raw request body for signature verification
            signature: X-Hub-Signature-256 header value

        Returns:
            True if handled successfully
        """
        # Verify signature
        if not self.verify_webhook_signature(raw_payload, signature):
            logger.warning("remote.github.invalid_signature")
            return False

        logger.debug(
            "remote.github.webhook_received",
            event_type=event_type,
            action=payload.get("action")
        )

        # Parse message based on event type
        message = self._parse_webhook_event(event_type, payload)

        if message and self.message_handler:
            message.metadata["platform"] = "github"
            message.metadata["event_type"] = event_type
            try:
                await self.message_handler(message)
            except Exception as e:
                logger.error(
                    "remote.github.handler_error",
                    error=str(e),
                    exc_info=True
                )

        return True

    def _parse_webhook_event(
        self,
        event_type: str,
        payload: dict
    ) -> Optional[PlatformMessage]:
        """
        Parse a webhook event into a PlatformMessage.

        Args:
            event_type: GitHub event type
            payload: Event payload

        Returns:
            PlatformMessage if relevant event, None otherwise
        """
        action = payload.get("action")

        # Handle issue comment events
        if event_type == "issue_comment" and action == "created":
            comment = payload.get("comment", {})
            issue = payload.get("issue", {})
            repo = payload.get("repository", {})
            sender = payload.get("sender", {})

            # Only handle comments that mention the bot or are commands
            body = comment.get("body", "")
            if not body.strip().startswith("/"):
                return None

            return PlatformMessage(
                message_id=str(comment.get("id", "")),
                conversation_id=f"{repo.get('full_name')}#{issue.get('number')}",
                sender_id=str(sender.get("id", "")),
                sender_name=sender.get("login"),
                content=body,
                message_type=MessageType.COMMAND,
                timestamp=datetime.fromisoformat(
                    comment.get("created_at", "").replace("Z", "+00:00")
                ) if comment.get("created_at") else datetime.utcnow(),
                raw_event=payload,
            )

        # Handle issue events
        elif event_type == "issues" and action in ("opened", "edited"):
            issue = payload.get("issue", {})
            repo = payload.get("repository", {})
            sender = payload.get("sender", {})

            body = issue.get("body", "")

            return PlatformMessage(
                message_id=str(issue.get("id", "")),
                conversation_id=f"{repo.get('full_name')}#{issue.get('number')}",
                sender_id=str(sender.get("id", "")),
                sender_name=sender.get("login"),
                content=body or issue.get("title", ""),
                message_type=MessageType.TEXT,
                timestamp=datetime.fromisoformat(
                    issue.get("created_at", "").replace("Z", "+00:00")
                ) if issue.get("created_at") else datetime.utcnow(),
                raw_event=payload,
            )

        # Handle pull request comment events
        elif event_type == "pull_request_review_comment" and action == "created":
            comment = payload.get("comment", {})
            pr = payload.get("pull_request", {})
            repo = payload.get("repository", {})
            sender = payload.get("sender", {})

            body = comment.get("body", "")
            if not body.strip().startswith("/"):
                return None

            return PlatformMessage(
                message_id=str(comment.get("id", "")),
                conversation_id=f"{repo.get('full_name')}#PR{pr.get('number')}",
                sender_id=str(sender.get("id", "")),
                sender_name=sender.get("login"),
                content=body,
                message_type=MessageType.COMMAND,
                timestamp=datetime.fromisoformat(
                    comment.get("created_at", "").replace("Z", "+00:00")
                ) if comment.get("created_at") else datetime.utcnow(),
                raw_event=payload,
            )

        return None

    def parse_message(self, raw_event: Any) -> Optional[PlatformMessage]:
        """
        Parse a raw event into a PlatformMessage.

        For GitHub, this is a wrapper around _parse_webhook_event.
        """
        if not isinstance(raw_event, dict):
            return None

        event_type = raw_event.get("event_type", "issues")
        return self._parse_webhook_event(event_type, raw_event)

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        reply_to_id: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """
        Send a comment to a GitHub issue or PR.

        Args:
            conversation_id: Format "owner/repo#number" or "owner/repo#PRnumber"
            message: Comment text (supports Markdown)
            reply_to_id: Not used for GitHub
            **kwargs: Additional parameters

        Returns:
            SendResult indicating success/failure
        """
        if not self._client:
            return SendResult(success=False, error="GitHub client not initialized")

        try:
            # Parse conversation_id
            if "#" not in conversation_id:
                return SendResult(
                    success=False,
                    error="Invalid conversation_id format. Expected: owner/repo#number"
                )

            repo_part, issue_part = conversation_id.split("#", 1)

            # Handle PR vs issue
            if issue_part.startswith("PR"):
                issue_number = issue_part[2:]
                endpoint = f"/repos/{repo_part}/pulls/{issue_number}/comments"
            else:
                issue_number = issue_part
                endpoint = f"/repos/{repo_part}/issues/{issue_number}/comments"

            client = await self._get_client()
            response = await client.post(endpoint, json={"body": message})

            if response.status_code in (200, 201):
                result = response.json()
                logger.info(
                    "remote.github.comment_sent",
                    repo=repo_part,
                    issue=issue_number
                )
                return SendResult(
                    success=True,
                    message_id=str(result.get("id", ""))
                )
            else:
                error = response.text
                logger.error(
                    "remote.github.send_failed",
                    status=response.status_code,
                    error=error
                )
                return SendResult(success=False, error=error)

        except Exception as e:
            logger.error(
                "remote.github.send_error",
                error=str(e)
            )
            return SendResult(success=False, error=str(e))

    async def send_typing(self, conversation_id: str) -> None:
        """
        Send a typing indicator.

        Note: GitHub doesn't support typing indicators.
        This is a no-op for interface compatibility.
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the GitHub API is accessible.

        Returns:
            True if healthy
        """
        if not self.token:
            return False

        try:
            client = await self._get_client()
            response = await client.get("/user")
            return response.status_code == 200
        except Exception:
            return False

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[list] = None
    ) -> Optional[dict]:
        """
        Create a new GitHub issue.

        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body (Markdown)
            labels: List of label names

        Returns:
            Created issue dict or None
        """
        client = await self._get_client()

        payload = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels

        try:
            response = await client.post(
                f"/repos/{owner}/{repo}/issues",
                json=payload
            )
            if response.status_code == 201:
                return response.json()
        except Exception as e:
            logger.error("remote.github.create_issue_failed", error=str(e))

        return None

    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int
    ) -> Optional[dict]:
        """
        Get issue details.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number

        Returns:
            Issue dict or None
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/issues/{issue_number}"
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning("remote.github.get_issue_failed", error=str(e))

        return None
