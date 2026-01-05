#!/usr/bin/env python3
"""
Cleanup Stale Sessions
======================

Utility to clean up stuck/stale sessions that are marked as 'running'
but are no longer active due to ungraceful shutdowns.

This is useful when:
- System was put to sleep or hibernated
- Process was killed without cleanup
- Session failed but status wasn't updated

Usage:
    python scripts/cleanup_sessions.py [--project PROJECT_NAME] [--force]
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import AgentOrchestrator
from core.database_connection import DatabaseManager


async def list_running_sessions():
    """List all sessions currently marked as running."""
    async with DatabaseManager() as db:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    s.id,
                    s.session_number,
                    s.type,
                    s.status,
                    s.started_at,
                    p.name as project_name,
                    EXTRACT(EPOCH FROM (NOW() - s.started_at))/60 as minutes_running
                FROM sessions s
                JOIN projects p ON s.project_id = p.id
                WHERE s.status = 'running'
                ORDER BY s.started_at DESC
                """
            )
            return [dict(row) for row in rows]


async def cleanup_stale_sessions(project_name: str = None, force: bool = False):
    """
    Cleanup stale sessions.

    Args:
        project_name: Optional project name to filter by
        force: If True, cleanup all running sessions regardless of time
    """
    orchestrator = AgentOrchestrator()

    # List current running sessions
    print("\n" + "="*80)
    print("Checking for stuck sessions...")
    print("="*80 + "\n")

    running = await list_running_sessions()

    if not running:
        print("✓ No running sessions found.\n")
        return 0

    # Filter by project if specified
    if project_name:
        running = [s for s in running if s['project_name'] == project_name]
        if not running:
            print(f"✓ No running sessions found for project '{project_name}'.\n")
            return 0

    # Display running sessions
    print(f"Found {len(running)} session(s) marked as running:\n")
    for session in running:
        minutes = session['minutes_running']
        started = session['started_at']
        print(f"  • Session {session['session_number']} ({session['type']}) in '{session['project_name']}'")
        print(f"    Started: {started} ({minutes:.1f} minutes ago)")

        # Determine if stale based on type
        thresholds = {
            'initializer': 30,
            'coding': 10,
            'review': 5,
        }
        threshold = thresholds.get(session['type'], 10)
        is_stale = minutes > threshold

        if is_stale:
            print(f"    Status: STALE (>{threshold} min threshold for {session['type']})")
        else:
            print(f"    Status: Active (<{threshold} min threshold)")
        print()

    # Cleanup
    if force:
        print("⚠️  Force mode enabled - will mark ALL running sessions as interrupted\n")
        confirmation = input("Are you sure you want to continue? (yes/no): ")
        if confirmation.lower() != 'yes':
            print("\nCancelled.")
            return 0

        # Force cleanup all running sessions
        async with DatabaseManager() as db:
            async with db.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE sessions
                    SET status = 'interrupted',
                        ended_at = COALESCE(ended_at, NOW()),
                        interruption_reason = 'Manually interrupted via cleanup tool (force)'
                    WHERE status = 'running'
                    """
                )
                count = int(result.split()[-1]) if result else 0
                print(f"\n✓ Marked {count} session(s) as interrupted (force mode)\n")
                return count
    else:
        # Normal cleanup (uses time-based thresholds)
        count = await orchestrator.cleanup_stale_sessions()

        if count > 0:
            print(f"✓ Marked {count} stale session(s) as interrupted\n")
        else:
            print("✓ No stale sessions found (all sessions are still within normal runtime)\n")
            print("💡 If you need to stop an active session, use --force flag\n")

        return count


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cleanup stuck/stale YokeFlow sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Cleanup stale sessions across all projects
  python scripts/cleanup_sessions.py

  # Cleanup stale sessions for specific project
  python scripts/cleanup_sessions.py --project my_project

  # Force cleanup ALL running sessions (even if not stale)
  python scripts/cleanup_sessions.py --force

Thresholds for automatic cleanup (without --force):
  - Initializer sessions: 30 minutes
  - Coding sessions: 10 minutes
  - Review sessions: 5 minutes
        """,
    )

    parser.add_argument(
        "--project",
        type=str,
        help="Only cleanup sessions for specific project name",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force cleanup all running sessions (ignores time thresholds)",
    )

    args = parser.parse_args()

    try:
        count = await cleanup_stale_sessions(
            project_name=args.project,
            force=args.force
        )
        sys.exit(0 if count >= 0 else 1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
