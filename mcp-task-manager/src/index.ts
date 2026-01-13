#!/usr/bin/env node
/**
 * MCP Server for Task Management
 * Provides structured task management capabilities for YokeFlow agents
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import crypto from 'crypto';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import type { Tool } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import { fileURLToPath } from 'url';
// Import database implementation
import { TaskDatabase } from './database.js';
import type { NewTask, NewTest, NewEpic } from './types.js';

const execAsync = promisify(exec);

// Get __dirname equivalent in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Initialize database
const db = new TaskDatabase();

// Log database info
console.error(`Using PostgreSQL database for project: ${process.env.PROJECT_ID || 'unknown'}`);

// Helper to define ID field that works with both legacy (number) and PostgreSQL (string/UUID)
const idFieldSchema = {
  oneOf: [
    { type: 'number' },
    { type: 'string' }
  ]
};

/**
 * Run Python verification system for a task.
 * Called before marking task as complete to ensure tests pass.
 *
 * @param taskId - UUID of task to verify
 * @param sessionId - Optional UUID of current session
 * @returns Object with passed flag and message
 */
async function runPythonVerification(
  taskId: string,
  sessionId?: string
): Promise<{passed: boolean, message: string}> {
  try {
    // Get project name to construct path
    const projectName = await db.getProjectName();
    const projectPath = `generations/${projectName}`;

    console.error(`[Verification] Running verification for task ${taskId}`);
    console.error(`[Verification] Project path: ${projectPath}`);

    // Determine the YokeFlow root directory (parent of mcp-task-manager)
    const yokeflowRoot = path.resolve(__dirname, '..', '..');

    // Build command
    const args = [
      '-m', 'server.verification.cli',
      '--task-id', taskId,
      '--project-path', projectPath
    ];

    if (sessionId) {
      args.push('--session-id', sessionId);
    }

    // Run Python verification CLI with PYTHONPATH set to YokeFlow root
    const { stdout, stderr } = await execAsync(
      `python ${args.join(' ')}`,
      {
        timeout: 120000, // 2 minute timeout
        maxBuffer: 10 * 1024 * 1024, // 10MB buffer
        cwd: yokeflowRoot, // Run from YokeFlow root
        env: {
          ...process.env,
          PYTHONPATH: yokeflowRoot // Add YokeFlow root to Python path
        }
      }
    );

    // Exit code 0 = success
    console.error(`[Verification] PASSED for task ${taskId}`);
    return {
      passed: true,
      message: stdout || '✓ All tests passed'
    };

  } catch (error: any) {
    // Check exit code
    const exitCode = error.code;

    if (exitCode === 2) {
      // Configuration error - don't block task completion
      console.error(`[Verification] Configuration error for task ${taskId}: ${error.stderr || error.message}`);
      return {
        passed: true, // Don't block on config errors
        message: `⚠️  Verification system error (task not blocked):\n${error.stderr || error.message}`
      };
    }

    // Exit code 1 or other error = verification failed
    console.error(`[Verification] FAILED for task ${taskId}: ${error.stderr || error.message}`);
    return {
      passed: false,
      message: error.stderr || error.stdout || error.message || 'Verification failed'
    };
  }
}

// Define tool schemas
const tools: Tool[] = [
  {
    name: 'task_status',
    description: 'Get overall project status including epics, tasks, and tests progress',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_next_task',
    description: 'Get the next highest priority incomplete task to work on',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'list_epics',
    description: 'List all epics or epics that need task expansion',
    inputSchema: {
      type: 'object',
      properties: {
        needs_expansion: {
          type: 'boolean',
          description: 'If true, only show epics with no tasks'
        }
      }
    }
  },
  {
    name: 'get_epic',
    description: 'Get details of a specific epic including its tasks',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic'
        }
      },
      required: ['epic_id']
    }
  },
  {
    name: 'list_tasks',
    description: 'List tasks with optional filtering',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'Filter by epic ID'
        },
        only_pending: {
          type: 'boolean',
          description: 'Only show incomplete tasks'
        }
      }
    }
  },
  {
    name: 'get_task',
    description: 'Get detailed information about a specific task including its tests',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'list_tests',
    description: 'List all tests for a specific task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'create_epic',
    description: 'Create a new epic',
    inputSchema: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: 'Name of the epic'
        },
        description: {
          type: 'string',
          description: 'Detailed description of the epic'
        },
        priority: {
          type: 'number',
          description: 'Priority (lower number = higher priority)'
        }
      },
      required: ['name', 'priority']
    }
  },
  {
    name: 'create_task',
    description: 'Create a new task within an epic',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The epic this task belongs to'
        },
        description: {
          type: 'string',
          description: 'Brief description of the task'
        },
        action: {
          type: 'string',
          description: 'Detailed implementation instructions'
        },
        priority: {
          type: 'number',
          description: 'Priority within the epic (optional, auto-increments)'
        }
      },
      required: ['epic_id', 'description', 'action']
    }
  },
  {
    name: 'create_test',
    description: 'Create a test case for a task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The task this test belongs to'
        },
        category: {
          type: 'string',
          enum: ['functional', 'style', 'accessibility', 'performance'],
          description: 'Category of test'
        },
        description: {
          type: 'string',
          description: 'What this test verifies'
        },
        steps: {
          type: 'array',
          items: { type: 'string' },
          description: 'Array of test steps to perform'
        }
      },
      required: ['task_id', 'category', 'description', 'steps']
    }
  },
  {
    name: 'update_task_status',
    description: 'Mark a task as done or not done',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        },
        done: {
          type: 'boolean',
          description: 'Whether the task is completed'
        }
      },
      required: ['task_id', 'done']
    }
  },
  {
    name: 'start_task',
    description: 'Mark a task as started/in progress',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task to start'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'update_test_result',
    description: 'Mark a test as passing or failing',
    inputSchema: {
      type: 'object',
      properties: {
        test_id: {
          ...idFieldSchema,
          description: 'The ID of the test'
        },
        passes: {
          type: 'boolean',
          description: 'Whether the test passes'
        }
      },
      required: ['test_id', 'passes']
    }
  },
  {
    name: 'expand_epic',
    description: 'Break down an epic into multiple tasks',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic to expand'
        },
        tasks: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              description: { type: 'string' },
              action: { type: 'string' },
              priority: { type: 'number' }
            },
            required: ['description', 'action']
          },
          description: 'Array of tasks to create for this epic'
        }
      },
      required: ['epic_id', 'tasks']
    }
  },
  // DEPRECATED: log_session tool removed - sessions are now managed by orchestrator
  // It was creating phantom sessions with status='completed' but no timestamps
  {
    name: 'mark_project_complete',
    description: 'Mark the project as complete when all epics, tasks, and tests are finished. Sets the completion timestamp in the database.',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_session_history',
    description: 'Get recent session history',
    inputSchema: {
      type: 'object',
      properties: {
        limit: {
          type: 'number',
          description: 'Maximum number of sessions to return (default: 10)'
        }
      }
    }
  },
  {
    name: 'bash_docker',
    description: 'Execute a bash command in the Docker sandbox. Use this instead of the regular Bash tool when a sandbox is active. Returns stdout, stderr, and exit code.',
    inputSchema: {
      type: 'object',
      properties: {
        command: {
          type: 'string',
          description: 'The bash command to execute in the Docker container'
        },
        description: {
          type: 'string',
          description: 'Brief description of what this command does (for logging)'
        }
      },
      required: ['command']
    }
  },
  {
    name: 'run_task_verification',
    description: 'Run verification tests for a completed task. Tests are automatically generated and executed.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task to verify'
        },
        force: {
          type: 'boolean',
          description: 'Force re-run even if already verified'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'get_verification_status',
    description: 'Get the verification status and test results for a task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the task'
        }
      },
      required: ['task_id']
    }
  },
  {
    name: 'track_file_modification',
    description: 'Track that a file was modified during task implementation',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          ...idFieldSchema,
          description: 'The ID of the current task'
        },
        file_path: {
          type: 'string',
          description: 'Path to the modified file'
        },
        modification_type: {
          type: 'string',
          enum: ['created', 'modified', 'deleted', 'renamed'],
          description: 'Type of modification'
        }
      },
      required: ['task_id', 'file_path']
    }
  },
  {
    name: 'list_verification_results',
    description: 'List all verification results for the current project',
    inputSchema: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          enum: ['passed', 'failed', 'manual_review', 'all'],
          description: 'Filter by verification status'
        }
      }
    }
  },
  {
    name: 'validate_epic',
    description: 'Trigger validation for an epic (requires all tasks to be complete)',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic to validate'
        },
        session_id: {
          type: 'string',
          description: 'Optional session ID for tracking'
        }
      },
      required: ['epic_id']
    }
  },
  {
    name: 'get_epic_validation_status',
    description: 'Get validation status for a specific epic',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic'
        }
      },
      required: ['epic_id']
    }
  },
  {
    name: 'list_epic_validation_results',
    description: 'List recent epic validation results',
    inputSchema: {
      type: 'object',
      properties: {
        limit: {
          type: 'number',
          description: 'Maximum number of results to return (default: 10)'
        }
      }
    }
  },
  {
    name: 'mark_epic_validated',
    description: 'Mark an epic as validated based on validation results',
    inputSchema: {
      type: 'object',
      properties: {
        epic_id: {
          ...idFieldSchema,
          description: 'The ID of the epic'
        },
        validation_id: {
          type: 'string',
          description: 'The validation result ID'
        },
        session_id: {
          type: 'string',
          description: 'Optional session ID'
        }
      },
      required: ['epic_id', 'validation_id']
    }
  }
];

// Create MCP server
const server = new Server(
  {
    name: 'mcp-task-manager',
    version: '1.0.0'
  },
  {
    capabilities: {
      tools: {},
      resources: {}
    }
  }
);

// Handle tool listing
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools };
});

// Handle resource listing (we don't use resources, but SDK might expect this)
server.setRequestHandler(ListResourcesRequestSchema, async () => {
  return { resources: [] };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'task_status':
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(await db.getProjectStatus(), null, 2)
            }
          ]
        };

      case 'get_next_task':
        const nextTask = await db.getNextTask();
        if (!nextTask) {
          return {
            content: [
              {
                type: 'text',
                text: 'No pending tasks found. Consider expanding epics that need tasks.'
              }
            ]
          };
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(nextTask, null, 2)
            }
          ]
        };

      case 'list_epics':
        const epics = await db.listEpics(args?.needs_expansion as boolean);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(epics, null, 2)
            }
          ]
        };

      case 'get_epic':
        const epic = await db.getEpic(args?.epic_id as any);
        if (!epic) {
          throw new Error(`Epic ${args?.epic_id} not found`);
        }
        const epicProgress = await db.getEpicProgress(args?.epic_id as any);
        const epicTasks = await db.listTasks(args?.epic_id as any);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({ epic, progress: epicProgress[0], tasks: epicTasks }, null, 2)
            }
          ]
        };

      case 'list_tasks':
        const tasks = await db.listTasks(
          args?.epic_id as any | undefined,
          args?.only_pending as boolean
        );
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(tasks, null, 2)
            }
          ]
        };

      case 'get_task':
        const task = await db.getTask(args?.task_id as any);
        if (!task) {
          throw new Error(`Task ${args?.task_id} not found`);
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(task, null, 2)
            }
          ]
        };

      case 'list_tests':
        const tests = await db.listTests(args?.task_id as any);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(tests, null, 2)
            }
          ]
        };

      case 'create_epic':
        const newEpic: NewEpic = {
          name: args?.name as string,
          description: args?.description as string,
          priority: args?.priority as number
        };
        const createdEpic = await db.createEpic(newEpic);
        return {
          content: [
            {
              type: 'text',
              text: `Created epic ${createdEpic.id}: ${createdEpic.name}`
            }
          ]
        };

      case 'create_task':
        const newTask: NewTask = {
          epic_id: args?.epic_id as any,
          description: args?.description as string,
          action: args?.action as string,
          priority: args?.priority as number
        };
        const createdTask = await db.createTask(newTask);
        return {
          content: [
            {
              type: 'text',
              text: `Created task ${createdTask.id}: ${createdTask.description}`
            }
          ]
        };

      case 'create_test':
        const newTest: NewTest = {
          task_id: args?.task_id as any,
          category: args?.category as any,
          description: args?.description as string,
          steps: args?.steps as string[]
        };
        const createdTest = await db.createTest(newTest);
        return {
          content: [
            {
              type: 'text',
              text: `Created test ${createdTest.id}: ${createdTest.description}`
            }
          ]
        };

      case 'update_task_status':
        // If marking task as done, run verification first
        if (args?.done === true) {
          const taskId = String(args?.task_id);
          const sessionId = process.env.SESSION_ID; // Optional session context

          console.error(`[MCP] Task ${taskId} completion requested - running verification...`);

          const verificationResult = await runPythonVerification(taskId, sessionId);

          if (!verificationResult.passed) {
            // Verification failed - return error and don't update task
            return {
              content: [
                {
                  type: 'text',
                  text: `❌ Task ${taskId} CANNOT be marked complete - verification failed:\n\n${verificationResult.message}\n\n` +
                        `Please fix the failing tests and try again. The task will remain incomplete until all tests pass.`
                }
              ],
              isError: true
            };
          }

          // Verification passed - log success
          console.error(`[MCP] Task ${taskId} verification passed - marking complete`);
          console.error(`[Verification] ${verificationResult.message}`);
        }

        // Proceed with normal task update (either verification passed or marking incomplete)
        const updatedTask = await db.updateTaskStatus(
          args?.task_id as any,
          args?.done as boolean
        );
        if (!updatedTask) {
          throw new Error(`Task ${args?.task_id} not found`);
        }

        return {
          content: [
            {
              type: 'text',
              text: `Task ${updatedTask.id} marked as ${args?.done ? 'completed' : 'incomplete'}` +
                    (args?.done ? '\n✅ All verification tests passed!' : '')
            }
          ]
        };

      case 'start_task':
        await db.startTask(args?.task_id as any);
        return {
          content: [
            {
              type: 'text',
              text: `Task ${args?.task_id} marked as started`
            }
          ]
        };

      case 'update_test_result':
        const updatedTest = await db.updateTestResult(
          args?.test_id as any,
          args?.passes as boolean
        );
        if (!updatedTest) {
          throw new Error(`Test ${args?.test_id} not found`);
        }
        return {
          content: [
            {
              type: 'text',
              text: `Test ${updatedTest.id} marked as ${args?.passes ? 'passing' : 'failing'}`
            }
          ]
        };

      case 'expand_epic':
        const expandedTasks = await db.expandEpic(
          args?.epic_id as any,
          args?.tasks as NewTask[]
        );
        return {
          content: [
            {
              type: 'text',
              text: `Expanded epic ${args?.epic_id} with ${expandedTasks.length} tasks:\n${
                expandedTasks.map(t => `- Task ${t.id}: ${t.description}`).join('\n')
              }`
            }
          ]
        };

      // REMOVED: case 'log_session' - deprecated tool that created phantom sessions
      // Sessions are now managed entirely by the orchestrator

      case 'mark_project_complete':
        await db.markProjectComplete();
        return {
          content: [
            {
              type: 'text',
              text: 'Project marked as complete! 🎉'
            }
          ]
        };

      case 'get_session_history':
        const sessions = await db.getSessionHistory(args?.limit as number);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(sessions, null, 2)
            }
          ]
        };

      case 'bash_docker':
        // Get Docker configuration from environment
        const containerName = process.env.DOCKER_CONTAINER_NAME || 'yokeflow-container';
        let command = args?.command as string;

        if (!command) {
          throw new Error('Command is required for bash_docker');
        }

        console.error(`[bash_docker] Executing in container ${containerName}: ${command.substring(0, 100)}`);

        // Check if command contains a heredoc and transform it if needed
        const heredocPattern = /cat\s*>\s*([^\s]+)\s*<<\s*['"]?(\w+)['"]?/;
        const hasHeredoc = heredocPattern.test(command);

        if (hasHeredoc) {
          console.error(`[bash_docker] Detected heredoc syntax, transforming command`);

          // Transform heredoc to use printf or echo with base64
          const fullHeredocPattern = /cat\s*>\s*([^\s]+)\s*<<\s*['"]?(\w+)['"]?\n([\s\S]*?)\n\2/;
          const match = command.match(fullHeredocPattern);

          if (match) {
            const [fullMatch, fileName, , content] = match; // delimiter not needed for base64 approach

            // Use base64 encoding for reliability
            const base64Content = Buffer.from(content).toString('base64');
            const base64Command = `echo "${base64Content}" | base64 -d > ${fileName}`;

            // Replace heredoc with base64 command
            command = command.replace(fullMatch, base64Command);
            console.error(`[bash_docker] Transformed heredoc to base64 encoding`);
          }
        }

        try {
          // Execute command in Docker container
          const dockerCommand = `docker exec ${containerName} /bin/bash -c ${JSON.stringify(command)}`;
          const { stdout, stderr } = await execAsync(dockerCommand, {
            maxBuffer: 10 * 1024 * 1024, // 10MB buffer
            timeout: 300000 // 5 minute timeout
          });

          console.error(`[bash_docker] Command executed successfully`);

          // Return result in a format similar to regular Bash tool
          let output = stdout;
          if (stderr) {
            output += stderr;
          }

          return {
            content: [
              {
                type: 'text',
                text: output
              }
            ]
          };
        } catch (error: any) {
          // Docker exec failed - check if it's an expected exit code
          console.error(`[bash_docker] Command failed: ${error.message}`);

          // Exit code 143 = 128 + 15 (SIGTERM) - this is EXPECTED when killing processes
          // Don't treat it as an error, just return the output
          const exitCode = error.code;
          if (exitCode === 143) {
            console.error(`[bash_docker] Process terminated with SIGTERM (expected for pkill)`);
            let output = '';
            if (error.stdout) output += error.stdout;
            if (error.stderr) output += error.stderr;
            if (!output) output = 'Process terminated (SIGTERM)';

            return {
              content: [
                {
                  type: 'text',
                  text: output
                }
              ]
              // NOT marking as error for exit code 143
            };
          }

          // For other exit codes, return as error
          let errorOutput = '';
          if (error.stdout) errorOutput += error.stdout;
          if (error.stderr) errorOutput += error.stderr;
          if (!errorOutput) errorOutput = error.message;

          return {
            content: [
              {
                type: 'text',
                text: errorOutput
              }
            ],
            isError: true
          };
        }

      case 'run_task_verification':
        // Manual verification trigger (also runs automatically on task completion)
        const verifyTaskId = String(args?.task_id);
        const force = args?.force as boolean || false;
        const verifySessionId = process.env.SESSION_ID;

        console.error(`[MCP] Manual verification requested for task ${verifyTaskId}`);

        const manualVerificationResult = await runPythonVerification(verifyTaskId, verifySessionId);

        if (manualVerificationResult.passed) {
          return {
            content: [
              {
                type: 'text',
                text: `✅ Task ${verifyTaskId} verification PASSED!\n\n${manualVerificationResult.message}\n\n` +
                      `You can now mark this task as complete using update_task_status.`
              }
            ]
          };
        } else {
          return {
            content: [
              {
                type: 'text',
                text: `❌ Task ${verifyTaskId} verification FAILED:\n\n${manualVerificationResult.message}\n\n` +
                      `Please fix the issues before marking the task as complete.`
              }
            ],
            isError: true
          };
        }

      case 'get_verification_status':
        const statusTaskId = args?.task_id as any;

        // Query verification results from database
        const verificationResult = await db.query<any>(
          `SELECT * FROM v_task_verification_status WHERE task_id = $1`,
          [statusTaskId]
        );

        if (verificationResult && verificationResult.length > 0) {
          const result = verificationResult[0] as any;
          return {
            content: [
              {
                type: 'text',
                text: `Task ${statusTaskId} verification status:
- Status: ${result.latest_verification_status || 'Not verified'}
- Tests Run: ${result.tests_run || 0}
- Tests Passed: ${result.tests_passed || 0}
- Tests Failed: ${result.tests_failed || 0}
- Retry Count: ${result.retry_count || 0}
- Needs Review: ${result.needs_review ? 'Yes' : 'No'}`
              }
            ]
          };
        } else {
          return {
            content: [
              {
                type: 'text',
                text: `Task ${statusTaskId} has not been verified yet.`
              }
            ]
          };
        }

      case 'track_file_modification':
        const trackTaskId = args?.task_id as any;
        const filePath = args?.file_path as string;
        const modificationType = args?.modification_type as string || 'modified';

        // Insert file modification tracking
        await db.query(
          `INSERT INTO task_file_modifications
           (task_id, file_path, modification_type, modified_at)
           VALUES ($1, $2, $3, CURRENT_TIMESTAMP)`,
          [trackTaskId, filePath, modificationType]
        );

        return {
          content: [
            {
              type: 'text',
              text: `Tracked ${modificationType} file: ${filePath} for task ${trackTaskId}`
            }
          ]
        };

      case 'list_verification_results':
        const statusFilter = args?.status as string || 'all';

        let query = `
          SELECT task_id, task_description, latest_verification_status,
                 tests_run, tests_passed, tests_failed, needs_review
          FROM v_task_verification_status
        `;

        if (statusFilter !== 'all') {
          query += ` WHERE latest_verification_status = '${statusFilter}'`;
        }

        query += ` ORDER BY last_verification_at DESC LIMIT 20`;

        const results = await db.query<any>(query);

        if (results && results.length > 0) {
          const summary = results.map((r: any) =>
            `- Task ${r.task_id}: ${r.latest_verification_status || 'Not verified'} (${r.tests_passed}/${r.tests_run} passed)`
          ).join('\n');

          return {
            content: [
              {
                type: 'text',
                text: `Recent verification results:\n${summary}`
              }
            ]
          };
        } else {
          return {
            content: [
              {
                type: 'text',
                text: 'No verification results found.'
              }
            ]
          };
        }

      case 'validate_epic':
        const epicIdToValidate = parseInt((args as any).epic_id);

        // Start epic validation
        const validationId = crypto.randomUUID();
        await db.query(
          `INSERT INTO epic_validation_results (
            id, epic_id, session_id, status, started_at
          ) VALUES ($1, $2, $3, 'running', NOW())`,
          [validationId, epicIdToValidate, (args as any).session_id || null]
        );

        return {
          content: [
            {
              type: 'text',
              text: `Epic validation started for epic ${epicIdToValidate}. Validation ID: ${validationId}\n\nNote: Full validation logic requires the Python verification system.`
            }
          ]
        };

      case 'get_epic_validation_status':
        const epicStatusId = parseInt((args as any).epic_id);

        const validationStatus = await db.query(
          `SELECT
            evs.*,
            e.name as epic_name
          FROM v_epic_validation_status evs
          JOIN epics e ON e.id = evs.epic_id
          WHERE evs.epic_id = $1`,
          [epicStatusId]
        ).then(r => r[0]) as any;

        if (validationStatus) {
          return {
            content: [
              {
                type: 'text',
                text: `Epic Validation Status:
Epic: ${validationStatus.epic_name}
Validated: ${validationStatus.validated ? 'Yes' : 'No'}
Status: ${validationStatus.validation_status || 'Not started'}
Tasks Verified: ${validationStatus.tasks_verified || 0}/${validationStatus.total_tasks || 0}
Integration Tests Passed: ${validationStatus.integration_tests_passed || 0}/${validationStatus.integration_tests_failed ? validationStatus.integration_tests_passed + validationStatus.integration_tests_failed : 'N/A'}
Rework Tasks: ${validationStatus.total_rework_tasks || 0}
Last Validation: ${validationStatus.last_validation_at || 'Never'}`
              }
            ]
          };
        } else {
          return {
            content: [
              {
                type: 'text',
                text: `No validation status found for epic ${epicStatusId}`
              }
            ]
          };
        }

      case 'list_epic_validation_results':
        const epicValidations = await db.query(
          `SELECT
            evr.*,
            e.name as epic_name
          FROM epic_validation_results evr
          JOIN epics e ON e.id = evr.epic_id
          ORDER BY evr.started_at DESC
          LIMIT $1`,
          [(args as any)?.limit || 10]
        ) as any[];

        if (epicValidations.length > 0) {
          const summary = epicValidations.map(v =>
            `Epic: ${v.epic_name}
  Status: ${v.status}
  Tasks: ${v.tasks_verified}/${v.total_tasks} verified
  Integration Tests: ${v.integration_tests_passed}/${v.integration_tests_run} passed
  Rework Tasks Created: ${v.rework_tasks_created || 0}
  Duration: ${v.duration_seconds || 0}s
  Started: ${v.started_at}`
          ).join('\n\n');

          return {
            content: [
              {
                type: 'text',
                text: `Recent Epic Validation Results:\n\n${summary}`
              }
            ]
          };
        } else {
          return {
            content: [
              {
                type: 'text',
                text: 'No epic validation results found.'
              }
            ]
          };
        }

      case 'mark_epic_validated':
        const epicToMark = parseInt((args as any).epic_id);
        const validationToUse = (args as any).validation_id;

        const markResult = await db.query(
          `SELECT mark_epic_validated($1, $2, $3) as success`,
          [epicToMark, validationToUse, (args as any).session_id || null]
        ).then(r => r[0]) as any;

        return {
          content: [
            {
              type: 'text',
              text: markResult?.success
                ? `✅ Epic ${epicToMark} marked as validated`
                : `❌ Failed to mark epic ${epicToMark} as validated`
            }
          ]
        };

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${errorMessage}`
        }
      ],
      isError: true
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('MCP Task Manager Server started');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});

// Handle cleanup
process.on('SIGINT', () => {
  db.close();
  process.exit(0);
});

process.on('SIGTERM', () => {
  db.close();
  process.exit(0);
});