"""
Simplified Tests for Database Operations
=========================================

Basic tests that verify the database operations are callable
without full mocking of the database layer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from server.database.operations import TaskDatabase
from server.database.connection import DatabaseManager


class TestDatabaseBasics:
    """Test basic database functionality."""

    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Test that database can be initialized."""
        db = TaskDatabase("postgresql://test:test@localhost/test")
        assert db.connection_url == "postgresql://test:test@localhost/test"
        assert db.pool is None

    @pytest.mark.asyncio
    async def test_database_manager_init(self):
        """Test DatabaseManager initialization."""
        with patch('server.database.connection.get_db') as mock_get_db:
            # Mock the database instance
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            # DatabaseManager only sets db when entering context
            db_manager = DatabaseManager("postgresql://test")
            assert db_manager.db is None  # Initially None

            # After entering context, db should be set
            async with db_manager as db:
                assert db is mock_db
                assert db_manager.db is mock_db


class TestDatabaseMethods:
    """Test that database methods exist and are callable."""

    def test_project_methods_exist(self):
        """Test that project methods exist."""
        db = TaskDatabase("postgresql://test")

        # Check methods exist
        assert hasattr(db, 'create_project')
        assert hasattr(db, 'get_project')
        assert hasattr(db, 'get_project_by_name')
        assert hasattr(db, 'list_projects')
        assert hasattr(db, 'update_project')
        assert hasattr(db, 'delete_project')
        assert hasattr(db, 'mark_project_complete')

    def test_session_methods_exist(self):
        """Test that session methods exist."""
        db = TaskDatabase("postgresql://test")

        assert hasattr(db, 'create_session')
        assert hasattr(db, 'start_session')
        assert hasattr(db, 'end_session')
        assert hasattr(db, 'get_active_session')
        assert hasattr(db, 'get_session_history')
        assert hasattr(db, 'cleanup_stale_sessions')

    def test_task_methods_exist(self):
        """Test that task methods exist."""
        db = TaskDatabase("postgresql://test")

        assert hasattr(db, 'create_task')
        assert hasattr(db, 'get_next_task')
        assert hasattr(db, 'update_task_status')
        assert hasattr(db, 'list_tasks')

    # Removed: test_quality_methods_exist() - store_quality_check() method removed
    # Quality metrics now stored in sessions.metrics JSONB field
    # Remaining quality methods: get_session_quality(), store_deep_review(), get_project_quality_summary()


class TestConnectionPool:
    """Test connection pool management."""

    @pytest.mark.asyncio
    async def test_connect_creates_pool(self):
        """Test that connect creates a connection pool."""
        mock_pool = AsyncMock()

        with patch('asyncpg.create_pool', new=AsyncMock(return_value=mock_pool)):
            db = TaskDatabase("postgresql://test")
            await db.connect()

            assert db.pool == mock_pool

    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self):
        """Test that disconnect closes the pool."""
        db = TaskDatabase("postgresql://test")
        db.pool = AsyncMock()

        await db.disconnect()
        db.pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_gets_connection(self):
        """Test acquiring a connection from pool."""
        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()
        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn

        async with db.acquire() as conn:
            assert conn == mock_conn

        db.pool.release.assert_called_once_with(mock_conn)


class TestProjectOperationsSimple:
    """Simple tests for project operations."""

    @pytest.mark.asyncio
    async def test_create_project_calls_database(self):
        """Test that create_project makes database call."""
        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            'id': uuid4(),
            'name': 'test',
            'spec_file_path': '/test',
            'created_at': datetime.now()
        }

        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn
        db.pool.release = AsyncMock()

        # This should not raise an error
        await db.create_project(
            name='test',
            spec_file_path='/test',
            spec_content='content'
        )

        # Verify database was called
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_projects_returns_list(self):
        """Test that list_projects returns a list."""
        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {'id': uuid4(), 'name': 'project1'},
            {'id': uuid4(), 'name': 'project2'}
        ]

        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn
        db.pool.release = AsyncMock()

        result = await db.list_projects()

        assert isinstance(result, list)
        assert len(result) == 2


class TestSessionOperationsSimple:
    """Simple tests for session operations."""

    @pytest.mark.asyncio
    async def test_create_session_requires_params(self):
        """Test that create_session requires proper parameters."""
        db = TaskDatabase("postgresql://test")

        # Should raise TypeError without required params
        with pytest.raises(TypeError):
            await db.create_session()

        # Should raise TypeError with missing params
        with pytest.raises(TypeError):
            await db.create_session(project_id=uuid4())

    @pytest.mark.asyncio
    async def test_start_session_updates_database(self):
        """Test that start_session updates the database."""
        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()

        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn
        db.pool.release = AsyncMock()

        session_id = uuid4()
        await db.start_session(session_id)

        # Should have called execute to update
        mock_conn.execute.assert_called_once()


class TestTaskOperationsSimple:
    """Simple tests for task operations."""

    @pytest.mark.asyncio
    async def test_update_task_status_params(self):
        """Test update_task_status parameter requirements."""
        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()

        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn
        db.pool.release = AsyncMock()

        # Should work with required params
        await db.update_task_status(
            task_id=123,
            done=True
        )

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_requires_project_id(self):
        """Test that list_tasks requires project_id."""
        db = TaskDatabase("postgresql://test")

        # Should raise TypeError without project_id
        with pytest.raises(TypeError):
            await db.list_tasks()


class TestErrorConditions:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_no_pool_raises_error(self):
        """Test that operations without pool raise error."""
        db = TaskDatabase("postgresql://test")
        # Don't set pool

        with pytest.raises(AttributeError):
            async with db.acquire():
                pass

    @pytest.mark.asyncio
    async def test_database_error_propagates(self):
        """Test that database errors propagate."""
        import asyncpg

        db = TaskDatabase("postgresql://test")
        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = asyncpg.PostgresError("Database error")

        db.pool = AsyncMock()
        db.pool.acquire.return_value = mock_conn
        db.pool.release = AsyncMock()

        with pytest.raises(asyncpg.PostgresError):
            await db.create_project(
                name='test',
                spec_file_path='/test'
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])