'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface RemoteStatus {
  telegram_enabled: boolean;
  telegram_bot_name?: string;
  active_conversations: number;
}

interface Conversation {
  id: string;
  platform: string;
  current_command: string | null;
  step: number;
  updated_at: string;
}

export default function RemoteControlPage() {
  const [status, setStatus] = useState<RemoteStatus | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [statusData, conversationsData] = await Promise.all([
        api.getRemoteStatus(),
        api.getRemoteConversations(),
      ]);
      setStatus(statusData);
      setConversations(conversationsData);
      setError(null);
    } catch (err: any) {
      if (err.response?.status === 503) {
        setError('Remote control not configured. Add TELEGRAM_BOT_TOKEN to your environment.');
      } else {
        setError('Failed to load remote control status');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleStartTelegram = async () => {
    setActionLoading('start');
    try {
      await api.startTelegramPolling();
      await loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start Telegram');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopTelegram = async () => {
    setActionLoading('stop');
    try {
      await api.stopTelegramPolling();
      await loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to stop Telegram');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSetCommands = async () => {
    setActionLoading('commands');
    try {
      await api.setTelegramCommands();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to set commands');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Remote Control</h1>
        <Button variant="outline" onClick={loadData}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">{error}</p>
        </div>
      )}

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500 dark:text-gray-400">
              Telegram
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Badge variant={status?.telegram_enabled ? 'default' : 'secondary'}>
                {status?.telegram_enabled ? 'Connected' : 'Disabled'}
              </Badge>
              {status?.telegram_bot_name && (
                <span className="text-sm text-gray-500">@{status.telegram_bot_name}</span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500 dark:text-gray-400">
              Active Conversations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{status?.active_conversations || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500 dark:text-gray-400">
              Slack / GitHub
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">Coming Soon</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Telegram Controls */}
      <Card>
        <CardHeader>
          <CardTitle>Telegram Controls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <Button
              onClick={handleStartTelegram}
              disabled={actionLoading !== null}
              variant="default"
            >
              {actionLoading === 'start' ? 'Starting...' : 'Start Polling'}
            </Button>
            <Button
              onClick={handleStopTelegram}
              disabled={actionLoading !== null}
              variant="outline"
            >
              {actionLoading === 'stop' ? 'Stopping...' : 'Stop Polling'}
            </Button>
            <Button
              onClick={handleSetCommands}
              disabled={actionLoading !== null}
              variant="outline"
            >
              {actionLoading === 'commands' ? 'Setting...' : 'Set Bot Commands'}
            </Button>
          </div>

          <div className="mt-6">
            <h4 className="font-medium mb-2">Setup Instructions</h4>
            <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600 dark:text-gray-400">
              <li>Message @BotFather on Telegram</li>
              <li>Send /newbot and follow instructions</li>
              <li>Copy the bot token to TELEGRAM_BOT_TOKEN in your .env</li>
              <li>Restart the YokeFlow API server</li>
              <li>Click "Start Polling" above</li>
            </ol>
          </div>

          <div className="mt-6">
            <h4 className="font-medium mb-2">Available Commands</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/status</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/projects</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/start</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/pause</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/resume</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/review</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/cancel</code>
              <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">/help</code>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Active Conversations */}
      <Card>
        <CardHeader>
          <CardTitle>Active Conversations</CardTitle>
        </CardHeader>
        <CardContent>
          {conversations.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400">No active conversations</p>
          ) : (
            <div className="space-y-3">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
                >
                  <div>
                    <div className="font-medium">{conv.id}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      Platform: {conv.platform}
                      {conv.current_command && ` • Command: /${conv.current_command}`}
                    </div>
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {new Date(conv.updated_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Future Platforms */}
      <Card>
        <CardHeader>
          <CardTitle>Coming Soon</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium mb-2">Slack Integration</h4>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Control YokeFlow from Slack channels and direct messages.
                Requires Slack App with Socket Mode enabled.
              </p>
            </div>
            <div>
              <h4 className="font-medium mb-2">GitHub Integration</h4>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Trigger YokeFlow via GitHub webhooks, issue comments,
                and pull request reviews.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
