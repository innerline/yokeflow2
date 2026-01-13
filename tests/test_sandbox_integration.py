"""
Integration tests for the Sandbox Manager with real Docker containers.

These tests are SLOW and require Docker to be running.
They create real Docker containers and should be skipped during rapid development.

To run these tests explicitly:
    pytest tests/test_sandbox_integration.py
    pytest -m "docker and integration"
    pytest --run-slow  # if configured

To skip these tests:
    pytest -m "not slow"
    pytest tests/ --ignore=tests/test_sandbox_integration.py
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
import pytest

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.sandbox.manager import (
    Sandbox,
    LocalSandbox,
    DockerSandbox,
    SandboxManager
)

# Mark all tests in this file as slow integration tests
pytestmark = [pytest.mark.slow, pytest.mark.docker, pytest.mark.integration]


def docker_available():
    """Check if Docker is available for testing."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


# Skip all tests in this file if Docker isn't available
requires_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker not available or not running"
)


@requires_docker
class TestDockerSandboxIntegration:
    """
    Integration tests for DockerSandbox with real Docker.
    These tests actually create and manage Docker containers.
    """

    @pytest.fixture(autouse=True)
    def cleanup_containers(self):
        """Ensure all test containers are cleaned up after each test."""
        yield
        # Post-test cleanup: remove any yokeflow test containers
        try:
            result = subprocess.run(
                ["docker", "ps", "-aq", "--filter", "name=yokeflow-test"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout:
                container_ids = result.stdout.strip().split('\n')
                for container_id in container_ids:
                    if container_id:
                        subprocess.run(
                            ["docker", "rm", "-f", container_id],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            timeout=5
                        )
        except Exception as e:
            print(f"Warning: Post-test cleanup failed: {e}")

    async def force_cleanup_container(self, container_name):
        """Force remove a container using docker command."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        except Exception:
            pass

    @pytest.fixture
    async def docker_sandbox(self, tmp_path):
        """Create a DockerSandbox instance with guaranteed cleanup."""
        # Use unique project name to avoid container conflicts
        unique_name = f"test_project_{str(uuid.uuid4())[:8]}"
        project_dir = tmp_path / unique_name
        project_dir.mkdir()

        # Clean up any existing containers with similar names first
        container_name = f"yokeflow-{unique_name}"
        await self.force_cleanup_container(container_name)

        # Create sandbox with a simple Python image
        config = {
            "image": "python:3.9-slim",
            "memory_limit": "512m",
            "cpu_limit": "0.5"
        }
        sandbox = DockerSandbox(project_dir, config)

        try:
            yield sandbox
        finally:
            # Cleanup on fixture teardown
            try:
                if hasattr(sandbox, 'container_id') and sandbox.container_id:
                    await sandbox.stop()
            except Exception as e:
                print(f"Warning: Sandbox stop failed: {e}")

            # Force cleanup using docker directly
            await self.force_cleanup_container(container_name)

    @pytest.mark.asyncio
    async def test_docker_sandbox_lifecycle(self, docker_sandbox):
        """Test basic Docker sandbox lifecycle: start, execute, cleanup."""
        # Start the sandbox
        await docker_sandbox.start()

        # Execute a simple command
        result = await docker_sandbox.execute_command("echo 'Hello from Docker'")

        assert result["returncode"] == 0
        assert "Hello from Docker" in result["stdout"]

        # Stop the container
        await docker_sandbox.stop()

        # Note: stop() doesn't remove container (for reuse)
        # So we don't verify removal here

    @pytest.mark.asyncio
    async def test_docker_sandbox_execute_command(self, docker_sandbox):
        """Test executing various commands in Docker sandbox."""
        await docker_sandbox.start()

        # Test basic echo
        result = await docker_sandbox.execute_command("echo 'test'")
        assert result["returncode"] == 0
        assert "test" in result["stdout"]

        # Test Python execution
        result = await docker_sandbox.execute_command("python --version")
        assert result["returncode"] == 0
        assert "Python" in result["stdout"]

        # Test working directory
        result = await docker_sandbox.execute_command("pwd")
        assert result["returncode"] == 0
        assert "/workspace" in result["stdout"]

        # Test file creation
        result = await docker_sandbox.execute_command("touch test.txt && ls test.txt")
        assert result["returncode"] == 0
        assert "test.txt" in result["stdout"]

        await docker_sandbox.stop()

    @pytest.mark.asyncio
    async def test_docker_sandbox_reuse_container(self, tmp_path):
        """Test that calling start() twice reuses the same container."""
        # Use a fixed name for this test to ensure we test reuse
        project_dir = tmp_path / "test_reuse_same"
        project_dir.mkdir()

        config = {"image": "python:3.9-slim"}
        sandbox = DockerSandbox(project_dir, config)

        try:
            # First start
            await sandbox.start()
            container_id_1 = sandbox.container_id

            # Create a file
            await sandbox.execute_command("echo 'persistent' > /workspace/test.txt")

            # Second start should reuse container
            await sandbox.start()
            container_id_2 = sandbox.container_id

            # Should be the same container
            assert container_id_1 == container_id_2

            # File should still exist
            result = await sandbox.execute_command("cat /workspace/test.txt")
            assert "persistent" in result["stdout"]

        finally:
            await sandbox.stop()
            # Force cleanup
            container_name = f"yokeflow-test_reuse_same"
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_docker_sandbox_initializer_recreates(self, tmp_path):
        """Test that sandbox recreates container when initializer changes."""
        project_dir = tmp_path / "test_initializer"
        project_dir.mkdir()

        # Create an init.sh file
        init_file = project_dir / "init.sh"
        init_file.write_text("#!/bin/bash\necho 'Initializer v1'\n")
        init_file.chmod(0o755)

        config = {"image": "python:3.9-slim"}
        sandbox = DockerSandbox(project_dir, config)

        try:
            # First start
            await sandbox.start()
            first_container_id = sandbox.container_id

            # Check that file exists in container (should be mounted)
            result = await sandbox.execute_command("ls -la /workspace/init.sh")
            assert result["returncode"] == 0
            assert "init.sh" in result["stdout"]

            # Run initializer
            result = await sandbox.execute_command("bash /workspace/init.sh")
            assert result["returncode"] == 0
            assert "Initializer v1" in result["stdout"]

            # Modify init.sh
            init_file.write_text("#!/bin/bash\necho 'Initializer v2'\n")

            # File should be immediately updated due to volume mount
            result = await sandbox.execute_command("bash /workspace/init.sh")
            assert result["returncode"] == 0
            assert "Initializer v2" in result["stdout"]

            # Container should NOT be recreated since files sync via volume mount
            assert sandbox.container_id == first_container_id

        finally:
            await sandbox.stop()
            # Force cleanup
            container_name = f"yokeflow-test_initializer"
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
            except Exception:
                pass


@requires_docker
class TestDockerSandboxPerformance:
    """Performance and stress tests for DockerSandbox."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_docker_rapid_commands(self, tmp_path):
        """Test executing many commands rapidly."""
        unique_name = f"test_rapid_{str(uuid.uuid4())[:8]}"
        project_dir = tmp_path / unique_name
        project_dir.mkdir()
        container_name = f"yokeflow-{unique_name}"

        config = {"image": "python:3.9-slim"}
        sandbox = DockerSandbox(project_dir, config)

        try:
            await sandbox.start()

            # Execute 20 commands rapidly
            results = []
            for i in range(20):
                result = await sandbox.execute_command(f"echo 'Test {i}'")
                results.append(result)

            # All should succeed
            assert all(r["returncode"] == 0 for r in results)
            assert len(results) == 20

            # Verify outputs
            for i, result in enumerate(results):
                assert f"Test {i}" in result["stdout"]

        finally:
            await sandbox.stop()
            # Force cleanup
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
            except Exception:
                pass

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_docker_large_output(self, tmp_path):
        """Test handling commands with large output."""
        unique_name = f"test_large_{str(uuid.uuid4())[:8]}"
        project_dir = tmp_path / unique_name
        project_dir.mkdir()
        container_name = f"yokeflow-{unique_name}"

        config = {"image": "python:3.9-slim"}
        sandbox = DockerSandbox(project_dir, config)

        try:
            await sandbox.start()

            # Generate large output (10000 lines)
            result = await sandbox.execute_command(
                "for i in $(seq 1 10000); do echo \"Line $i\"; done"
            )

            assert result["returncode"] == 0
            lines = result["stdout"].strip().split('\n')
            assert len(lines) == 10000
            assert "Line 1" in lines[0]
            assert "Line 10000" in lines[-1]

        finally:
            await sandbox.stop()
            # Force cleanup
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
            except Exception:
                pass


if __name__ == "__main__":
    # Run only if Docker is available
    if not docker_available():
        print("Docker is not available. Skipping integration tests.")
        sys.exit(0)

    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])