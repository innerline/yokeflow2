#!/usr/bin/env python3
"""
Container Cleanup Utility
==========================

Cleans up Docker containers for YokeFlow projects.

Containers are kept running between sessions for speed, but accumulate over time.
This utility helps remove containers for deleted or completed projects.

Usage:
    python scripts/cleanup_containers.py                    # Remove containers for deleted projects
    python scripts/cleanup_containers.py --all              # List all containers
    python scripts/cleanup_containers.py --stopped          # Remove all stopped containers
    python scripts/cleanup_containers.py --force            # Force remove ALL containers (including running)
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.database.connection import DatabaseManager


async def list_containers():
    """List all yokeflow containers."""
    import subprocess

    result = subprocess.run(
        ['docker', 'ps', '-a', '--filter', 'name=yokeflow',
         '--format', '{{.Names}}\t{{.Status}}\t{{.Size}}'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("Error: Failed to list Docker containers")
        print("Make sure Docker is running")
        return []

    lines = result.stdout.strip().split('\n')
    if not lines or lines == ['']:
        return []

    containers = []
    for line in lines:
        if '\t' in line:
            parts = line.split('\t')
            containers.append({
                'name': parts[0],
                'status': parts[1],
                'size': parts[2] if len(parts) > 2 else 'Unknown'
            })

    return containers


async def get_active_projects():
    """Get list of active project names from database."""
    async with DatabaseManager() as db:
        async with db.acquire() as conn:
            rows = await conn.fetch("SELECT name FROM projects")
            return [row['name'] for row in rows]


async def remove_container(container_name: str, force: bool = False) -> bool:
    """Remove a Docker container."""
    import subprocess

    cmd = ['docker', 'rm']
    if force:
        cmd.append('-f')
    cmd.append(container_name)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


async def cleanup_containers(stopped_only: bool = False, force: bool = False, all_containers: bool = False):
    """
    Cleanup Docker containers.

    Args:
        stopped_only: Only remove stopped containers
        force: Force remove (including running containers)
        all_containers: Just list all containers, don't remove
    """
    print("\n" + "="*80)
    print("YokeFlow Container Cleanup")
    print("="*80 + "\n")

    # List all containers
    containers = await list_containers()

    if not containers:
        print("✓ No yokeflow containers found.\n")
        return 0

    print(f"Found {len(containers)} container(s):\n")

    # Display containers
    for container in containers:
        name = container['name']
        status = container['status']
        size = container['size']

        running = "Up" in status
        status_icon = "🟢" if running else "⚪"

        print(f"  {status_icon} {name}")
        print(f"     Status: {status}")
        print(f"     Size: {size}")
        print()

    # If just listing, exit
    if all_containers:
        return 0

    # Get active projects from database
    try:
        active_projects = await get_active_projects()
        active_project_containers = {f"yokeflow-{name}" for name in active_projects}
    except Exception as e:
        print(f"Warning: Could not connect to database: {e}")
        print("Will use container status only for cleanup decisions.\n")
        active_project_containers = set()

    # Determine which containers to remove
    to_remove = []

    for container in containers:
        name = container['name']
        status = container['status']
        running = "Up" in status

        # Extract project name
        project_name = name.replace("yokeflow-", "")

        if force:
            # Force mode: remove all
            to_remove.append((name, "force"))
        elif stopped_only:
            # Stopped only mode: remove if not running
            if not running:
                to_remove.append((name, "stopped"))
        elif name not in active_project_containers:
            # Default mode: remove if no matching database project
            to_remove.append((name, f"no project '{project_name}' in database"))

    if not to_remove:
        print("✓ No containers to remove.\n")
        if not stopped_only and not force:
            print("💡 All containers belong to active projects")
            print("   Use --stopped to remove stopped containers")
            print("   Use --force to remove all containers\n")
        return 0

    # Confirmation
    print(f"Will remove {len(to_remove)} container(s):\n")
    for name, reason in to_remove:
        print(f"  • {name}")
        print(f"    Reason: {reason}")
    print()

    if not force and not stopped_only:
        confirmation = input("Continue? (yes/no): ")
        if confirmation.lower() != 'yes':
            print("\nCancelled.")
            return 0
    elif force:
        confirmation = input("⚠️  Force mode - this will remove running containers. Continue? (yes/no): ")
        if confirmation.lower() != 'yes':
            print("\nCancelled.")
            return 0

    # Remove containers
    print()
    removed = 0
    failed = 0

    for name, reason in to_remove:
        success = await remove_container(name, force=True)
        if success:
            print(f"✓ Removed: {name}")
            removed += 1
        else:
            print(f"✗ Failed: {name}")
            failed += 1

    print(f"\n✓ Removed {removed} container(s)")
    if failed > 0:
        print(f"✗ Failed to remove {failed} container(s)")

    print()
    return removed


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cleanup YokeFlow Docker containers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all containers
  python scripts/cleanup_containers.py --all

  # Remove containers for deleted projects (default)
  python scripts/cleanup_containers.py

  # Remove all stopped containers
  python scripts/cleanup_containers.py --stopped

  # Force remove ALL containers (including running)
  python scripts/cleanup_containers.py --force

Containers are kept running between sessions for speed. Over time, they
accumulate. This tool helps clean up containers for deleted/completed projects.
        """,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="List all containers (don't remove anything)",
    )

    parser.add_argument(
        "--stopped",
        action="store_true",
        help="Remove all stopped containers",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force remove all yokeflow containers (including running)",
    )

    args = parser.parse_args()

    try:
        count = await cleanup_containers(
            stopped_only=args.stopped,
            force=args.force,
            all_containers=args.all
        )
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
