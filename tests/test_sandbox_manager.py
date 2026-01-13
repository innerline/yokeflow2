"""
Unit tests for the Sandbox Manager.

These are fast tests that use mocks instead of real Docker containers.
For integration tests with real Docker, see test_sandbox_integration.py.

To run only these fast tests:
    pytest tests/test_sandbox_manager.py
    pytest -m "not slow"
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.sandbox.manager import (
    Sandbox,
    LocalSandbox,
    DockerSandbox,
    SandboxManager
)


@pytest.mark.unit
class TestDockerSandboxUnit:
    """Unit tests for DockerSandbox using mocks (no real Docker needed)."""

    @pytest.fixture
    def docker_sandbox(self, tmp_path):
        """Create a DockerSandbox instance for testing without Docker."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        config = {
            "image": "test-image:latest",
            "memory_limit": "1g",
            "cpu_limit": "1.0",
            "ports": ["3000:3000"],
            "session_type": "coding"
        }
        return DockerSandbox(project_dir, config)

    def test_docker_sandbox_init(self, docker_sandbox):
        """Test DockerSandbox initialization."""
        assert docker_sandbox.image == "test-image:latest"
        assert docker_sandbox.memory_limit == "1g"
        assert docker_sandbox.cpu_limit == "1.0"
        assert docker_sandbox.port_mappings == ["3000:3000"]
        assert docker_sandbox.session_type == "coding"

    def test_docker_sandbox_get_working_directory(self, docker_sandbox):
        """Test getting working directory for DockerSandbox."""
        working_dir = docker_sandbox.get_working_directory()
        assert working_dir == "/workspace"

    def test_docker_sandbox_host_path_conversion(self, docker_sandbox):
        """Test Docker-in-Docker path conversion."""
        # Test without HOST_GENERATIONS_PATH
        path = docker_sandbox._get_host_project_path()
        assert path == str(docker_sandbox.project_dir.resolve())

        # Test with HOST_GENERATIONS_PATH
        os.environ["HOST_GENERATIONS_PATH"] = "/host/generations"

        # Mock container path
        docker_sandbox.project_dir = Path("/app/generations/test_project")
        path = docker_sandbox._get_host_project_path()

        # Should convert to host path
        assert path == "/host/generations/test_project"

        # Clean up
        del os.environ["HOST_GENERATIONS_PATH"]

    @pytest.mark.asyncio
    async def test_docker_sandbox_start_with_mock(self, docker_sandbox):
        """Test Docker sandbox start with mocked Docker client."""
        # Since docker is imported inside the method, we need to patch it globally
        with patch('docker.from_env') as mock_from_env, \
             patch('docker.DockerClient') as mock_docker_client, \
             patch('subprocess.run') as mock_run, \
             patch.object(docker_sandbox, '_setup_container', new_callable=AsyncMock), \
             patch.object(docker_sandbox, '_cleanup_container', new_callable=AsyncMock):

            # Mock docker context check - needs to return JSON array with Endpoints
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps([{
                "Name": "default",
                "Current": True,
                "Endpoints": {
                    "docker": {
                        "Host": "unix:///var/run/docker.sock"
                    }
                }
            }])

            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_container.id = "test-container-id"
            mock_container.name = "test-container"
            mock_container.status = "running"
            mock_container.reload = MagicMock()
            mock_container.exec_run = MagicMock(return_value=(0, b"test output"))

            # Setup mock client
            mock_client.containers.list.return_value = []
            mock_client.containers.run.return_value = mock_container

            # Mock containers.get to raise NotFound first (no existing container), then return container for health checks
            import docker.errors
            get_calls = [docker.errors.NotFound("Container not found"), mock_container]
            mock_client.containers.get.side_effect = get_calls

            # Both constructors return the same mock client
            mock_from_env.return_value = mock_client
            mock_docker_client.return_value = mock_client

            # Start the sandbox
            await docker_sandbox.start()

            # Verify Docker client was created and container was started
            assert mock_from_env.called or mock_docker_client.called
            mock_client.containers.run.assert_called_once()

            # Verify container_id is set
            assert docker_sandbox.container_id == "test-container-id"
            assert docker_sandbox.is_running is True

    @pytest.mark.asyncio
    async def test_docker_sandbox_execute_with_mock(self, docker_sandbox):
        """Test command execution with mocked Docker container."""
        # Mock container
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.reload = MagicMock()

        # exec_run returns (exit_code, (stdout, stderr)) when demux=True
        mock_container.exec_run.return_value = (0, (b"Hello from mock", b""))

        # Mock client
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        # Set container_id and client for execute to work
        docker_sandbox.container_id = "test-container-id"
        docker_sandbox.client = mock_client

        # Execute command
        result = await docker_sandbox.execute_command("echo 'Hello'")

        # Verify result
        assert result["returncode"] == 0
        assert "Hello from mock" in result["stdout"]
        mock_container.exec_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_docker_sandbox_error_handling(self, docker_sandbox):
        """Test error handling in Docker operations."""
        # Mock both subprocess.run (for docker context) and docker clients
        with patch('subprocess.run') as mock_run, \
             patch('docker.DockerClient') as mock_client, \
             patch('docker.from_env') as mock_from_env:

            # Make docker context command fail
            mock_run.return_value.returncode = 1
            # Make both docker client methods fail
            mock_client.side_effect = Exception("Docker not available")
            mock_from_env.side_effect = Exception("Docker not available")

            with pytest.raises(RuntimeError) as exc_info:
                await docker_sandbox.start()

            assert "Failed to start Docker sandbox" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_docker_sandbox_stop_with_mock(self, docker_sandbox):
        """Test Docker sandbox stop with mocked container."""
        # Mock container
        mock_container = MagicMock()
        mock_container.name = "test-container"
        mock_container.stop = MagicMock()
        mock_container.remove = MagicMock()

        docker_sandbox.container_id = "test-container-id"
        docker_sandbox.container_name = "test-container"
        docker_sandbox.client = MagicMock()
        docker_sandbox.is_running = True

        # Stop
        await docker_sandbox.stop()

        # Verify stop() clears the sandbox state (even though container is kept for reuse)
        # The container itself remains for reuse, but the sandbox object state is cleared
        assert docker_sandbox.container_id is None
        assert docker_sandbox.client is None
        assert docker_sandbox.is_running is False

    @pytest.mark.asyncio
    async def test_docker_sandbox_is_healthy_no_container(self, docker_sandbox):
        """Test is_healthy when no container exists."""
        assert await docker_sandbox.is_healthy() is False

    @pytest.mark.asyncio
    async def test_docker_sandbox_is_healthy_with_container(self, docker_sandbox):
        """Test is_healthy with running container."""
        mock_container = MagicMock()
        mock_container.reload = MagicMock()
        mock_container.status = "running"

        # Mock client to return the container
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        # Need container_id and client for is_healthy to work
        docker_sandbox.container_id = "test-container-id"
        docker_sandbox.client = mock_client
        assert await docker_sandbox.is_healthy() is True

        # Test with stopped container
        mock_container.status = "exited"
        assert await docker_sandbox.is_healthy() is False


@pytest.mark.unit
class TestSandboxManager:
    """Test suite for the SandboxManager factory."""

    def test_create_local_sandbox(self, tmp_path):
        """Test creating a LocalSandbox through the manager."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        sandbox = SandboxManager.create_sandbox(
            sandbox_type="local",
            project_dir=project_dir
        )

        assert isinstance(sandbox, LocalSandbox)
        assert sandbox.project_dir == project_dir

    def test_create_docker_sandbox(self, tmp_path):
        """Test creating a DockerSandbox through the manager."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        config = {
            "image": "custom-image:latest",
            "memory_limit": "4g"
        }

        sandbox = SandboxManager.create_sandbox(
            sandbox_type="docker",
            project_dir=project_dir,
            config=config
        )

        assert isinstance(sandbox, DockerSandbox)
        assert sandbox.project_dir == project_dir
        assert sandbox.image == "custom-image:latest"
        assert sandbox.memory_limit == "4g"

    def test_create_unknown_sandbox_type(self, tmp_path):
        """Test that unknown sandbox types raise an error."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        with pytest.raises(ValueError) as excinfo:
            SandboxManager.create_sandbox(
                sandbox_type="unknown",
                project_dir=project_dir
            )

        assert "Unknown sandbox type" in str(excinfo.value)


@pytest.mark.unit
class TestSandboxBase:
    """Test the abstract Sandbox base class."""

    def test_sandbox_abstract_methods(self):
        """Test that Sandbox cannot be instantiated directly."""
        # Try to instantiate the abstract base class
        with pytest.raises(TypeError) as excinfo:
            sandbox = Sandbox(Path("/test"), {})

        assert "Can't instantiate abstract class" in str(excinfo.value)


@pytest.mark.unit
class TestLocalSandbox:
    """Test suite for LocalSandbox."""

    @pytest.fixture
    def local_sandbox(self, tmp_path):
        """Create a LocalSandbox instance for testing."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        return LocalSandbox(project_dir)

    @pytest.mark.asyncio
    async def test_local_sandbox_start(self, local_sandbox):
        """Test LocalSandbox start (should be no-op)."""
        # Start should complete without error
        await local_sandbox.start()
        # LocalSandbox doesn't need any setup

    @pytest.mark.asyncio
    async def test_local_sandbox_execute(self, local_sandbox):
        """Test command execution in LocalSandbox."""
        # Mock subprocess.run
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "test output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = await local_sandbox.execute_command("echo 'test'")

            assert result["returncode"] == 0
            assert "test output" in result["stdout"]
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_local_sandbox_stop(self, local_sandbox):
        """Test LocalSandbox stop (should be no-op)."""
        # Stop should complete without error
        await local_sandbox.stop()
        # LocalSandbox doesn't need cleanup

    def test_local_sandbox_working_directory(self, local_sandbox):
        """Test getting working directory for LocalSandbox."""
        working_dir = local_sandbox.get_working_directory()
        assert working_dir == str(local_sandbox.project_dir)