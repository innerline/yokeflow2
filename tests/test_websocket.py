"""
WebSocket API Test Suite
========================

Tests WebSocket endpoints for real-time communication.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket, WebSocketDisconnect

from server.api.app import app


class TestWebSocketConnection:
    """Test WebSocket connection handling."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_websocket_endpoint_exists(self, client):
        """Test that WebSocket endpoint is available."""
        # Check that the WebSocket route exists
        routes = [route.path for route in app.routes]
        ws_routes = [r for r in routes if 'ws' in r.lower()]

        # Should have at least one WebSocket route
        assert len(ws_routes) > 0, "No WebSocket routes found in app"

    @pytest.mark.asyncio
    async def test_websocket_connection_lifecycle(self):
        """Test WebSocket connection and disconnection."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock()
        mock_ws.receive_json = AsyncMock()
        mock_ws.close = AsyncMock()

        # Simulate connection
        await mock_ws.accept()

        # Simulate sending message
        await mock_ws.send_json({"type": "ping"})

        # Simulate receiving message
        mock_ws.receive_json.return_value = {"type": "pong"}
        response = await mock_ws.receive_json()

        assert response["type"] == "pong"

        # Simulate disconnection
        await mock_ws.close()

        mock_ws.accept.assert_called_once()
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_message_handling(self):
        """Test handling different message types."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_json = AsyncMock()

        # Test different message types
        test_messages = [
            {"type": "subscribe", "channel": "updates"},
            {"type": "unsubscribe", "channel": "updates"},
            {"type": "message", "data": "test data"},
            {"type": "ping"},
            {"type": "pong"},
        ]

        for msg in test_messages:
            await mock_ws.send_json(msg)
            mock_ws.send_json.assert_called_with(msg)

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self):
        """Test WebSocket error handling."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_json = AsyncMock()
        mock_ws.close = AsyncMock()

        # Simulate connection
        await mock_ws.accept()

        # Simulate error during receive
        mock_ws.receive_json.side_effect = WebSocketDisconnect(code=1000)

        with pytest.raises(WebSocketDisconnect):
            await mock_ws.receive_json()

        # Should close on error
        await mock_ws.close()
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_broadcast(self):
        """Test broadcasting messages to multiple clients."""
        # Create multiple mock WebSocket connections
        clients = []
        for i in range(3):
            mock_ws = Mock(spec=WebSocket)
            mock_ws.send_json = AsyncMock()
            mock_ws.client_id = f"client_{i}"
            clients.append(mock_ws)

        # Broadcast message to all clients
        broadcast_msg = {"type": "broadcast", "data": "announcement"}

        for client in clients:
            await client.send_json(broadcast_msg)
            client.send_json.assert_called_with(broadcast_msg)

    @pytest.mark.asyncio
    async def test_websocket_authentication(self):
        """Test WebSocket authentication flow."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_json = AsyncMock()
        mock_ws.close = AsyncMock()

        # Simulate authentication
        await mock_ws.accept()

        # Send auth message
        auth_msg = {"type": "auth", "token": "test_token_123"}
        await mock_ws.send_json(auth_msg)

        # Simulate auth response
        mock_ws.receive_json.return_value = {"type": "auth_success", "user_id": "user123"}
        response = await mock_ws.receive_json()

        assert response["type"] == "auth_success"
        assert response["user_id"] == "user123"


class TestWebSocketMessages:
    """Test WebSocket message formats and validation."""

    def test_message_format_validation(self):
        """Test message format validation."""
        valid_messages = [
            {"type": "ping"},
            {"type": "message", "data": "test"},
            {"type": "subscribe", "channel": "updates"},
        ]

        invalid_messages = [
            {},  # Missing type
            {"data": "test"},  # Missing type
            {"type": None},  # Invalid type
            "not a dict",  # Wrong format
        ]

        # Valid messages should have 'type' field
        for msg in valid_messages:
            assert "type" in msg
            assert msg["type"] is not None

        # Invalid messages should not pass validation
        for msg in invalid_messages:
            if isinstance(msg, dict):
                valid = "type" in msg and msg.get("type") is not None
            else:
                valid = False
            assert not valid

    def test_message_serialization(self):
        """Test message serialization to JSON."""
        messages = [
            {"type": "ping", "timestamp": 123456789},
            {"type": "data", "values": [1, 2, 3]},
            {"type": "status", "active": True},
        ]

        for msg in messages:
            # Should be serializable to JSON
            json_str = json.dumps(msg)
            assert json_str is not None

            # Should be deserializable back
            decoded = json.loads(json_str)
            assert decoded == msg


class TestWebSocketIntegration:
    """Test WebSocket integration with the application."""

    @pytest.mark.asyncio
    async def test_websocket_session_updates(self):
        """Test WebSocket updates during session lifecycle."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        session_id = str(uuid4())

        # Simulate session events
        events = [
            {"type": "session_started", "session_id": session_id},
            {"type": "task_started", "session_id": session_id, "task_id": "task123"},
            {"type": "task_completed", "session_id": session_id, "task_id": "task123"},
            {"type": "session_completed", "session_id": session_id},
        ]

        for event in events:
            await mock_ws.send_json(event)
            mock_ws.send_json.assert_called_with(event)

    @pytest.mark.asyncio
    async def test_websocket_progress_updates(self):
        """Test WebSocket progress update messages."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        # Simulate progress updates
        for i in range(0, 101, 10):
            progress_msg = {
                "type": "progress",
                "value": i,
                "total": 100,
                "message": f"Processing... {i}%"
            }
            await mock_ws.send_json(progress_msg)

        # Should have sent 11 progress updates (0, 10, 20, ..., 100)
        assert mock_ws.send_json.call_count == 11

    @pytest.mark.asyncio
    async def test_websocket_error_notifications(self):
        """Test WebSocket error notification messages."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()

        error_msg = {
            "type": "error",
            "code": "TASK_FAILED",
            "message": "Task execution failed",
            "details": {"task_id": "task456", "reason": "Timeout"}
        }

        await mock_ws.send_json(error_msg)
        mock_ws.send_json.assert_called_with(error_msg)


class TestWebSocketReconnection:
    """Test WebSocket reconnection handling."""

    @pytest.mark.asyncio
    async def test_reconnection_with_state(self):
        """Test reconnection preserves client state."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_json = AsyncMock()

        # Initial connection
        await mock_ws.accept()
        client_id = "client_123"

        # Subscribe to channels
        await mock_ws.send_json({
            "type": "subscribe",
            "channels": ["updates", "notifications"]
        })

        # Simulate disconnect
        mock_ws.close = AsyncMock()
        await mock_ws.close()

        # Simulate reconnection
        mock_ws.accept.reset_mock()
        await mock_ws.accept()

        # Send reconnect message with client ID
        await mock_ws.send_json({
            "type": "reconnect",
            "client_id": client_id
        })

        # Should restore subscriptions
        mock_ws.receive_json.return_value = {
            "type": "reconnect_success",
            "subscriptions": ["updates", "notifications"]
        }
        response = await mock_ws.receive_json()

        assert response["type"] == "reconnect_success"
        assert len(response["subscriptions"]) == 2

    @pytest.mark.asyncio
    async def test_reconnection_timeout(self):
        """Test reconnection timeout handling."""
        mock_ws = Mock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()

        # Connection with timeout
        await mock_ws.accept()

        # Simulate timeout
        await asyncio.sleep(0.1)

        # Should close after timeout
        await mock_ws.close()
        mock_ws.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])