'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { debounce } from 'lodash';

interface SpecEditorProps {
  value: string;
  onChange: (value: string) => void;
  onValidate?: (spec: string) => void;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}

export default function SpecEditor({
  value,
  onChange,
  onValidate,
  className = '',
  placeholder = 'Enter your specification here...',
  disabled = false
}: SpecEditorProps) {
  const [isPreview, setIsPreview] = useState(false);
  const [localValue, setLocalValue] = useState(value);
  const [wordCount, setWordCount] = useState(0);
  const [lineCount, setLineCount] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Update local value when prop changes
  useEffect(() => {
    setLocalValue(value);
    updateStats(value);
  }, [value]);

  // Update stats
  const updateStats = (text: string) => {
    const words = text.trim().split(/\s+/).filter(word => word.length > 0);
    setWordCount(words.length);
    setLineCount(text.split('\n').length);
  };

  // Debounced validation
  const debouncedValidate = useCallback(
    debounce((spec: string) => {
      if (onValidate) {
        onValidate(spec);
      }
    }, 1000),
    [onValidate]
  );

  // Handle text changes
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    onChange(newValue);
    updateStats(newValue);
    debouncedValidate(newValue);
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current && !isPreview) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [localValue, isPreview]);

  // Format markdown for preview
  const formatMarkdown = (text: string): string => {
    // Basic markdown parsing for preview
    let formatted = text;

    // Headers
    formatted = formatted.replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mt-4 mb-2 text-gray-200">$1</h3>');
    formatted = formatted.replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold mt-6 mb-3 text-gray-100">$1</h2>');
    formatted = formatted.replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-8 mb-4 text-white">$1</h1>');

    // Bold
    formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-100">$1</strong>');

    // Italic
    formatted = formatted.replace(/\*(.+?)\*/g, '<em class="italic">$1</em>');

    // Code blocks
    formatted = formatted.replace(/```([^`]+)```/g, '<pre class="bg-gray-900 p-3 rounded my-3 overflow-x-auto"><code class="text-sm text-gray-300">$1</code></pre>');

    // Inline code
    formatted = formatted.replace(/`([^`]+)`/g, '<code class="bg-gray-800 px-1 py-0.5 rounded text-sm text-blue-300">$1</code>');

    // Lists
    formatted = formatted.replace(/^\* (.+)$/gim, '<li class="ml-4 list-disc text-gray-300">$1</li>');
    formatted = formatted.replace(/^\- (.+)$/gim, '<li class="ml-4 list-disc text-gray-300">$1</li>');
    formatted = formatted.replace(/^\d+\. (.+)$/gim, '<li class="ml-4 list-decimal text-gray-300">$1</li>');

    // Wrap consecutive list items
    formatted = formatted.replace(/(<li.*<\/li>\n?)+/g, (match) => {
      const isOrdered = match.includes('list-decimal');
      const tag = isOrdered ? 'ol' : 'ul';
      return `<${tag} class="my-3 space-y-1">${match}</${tag}>`;
    });

    // Paragraphs
    formatted = formatted.split('\n\n').map(paragraph => {
      if (paragraph.trim() && !paragraph.includes('<h') && !paragraph.includes('<ul') && !paragraph.includes('<ol') && !paragraph.includes('<pre')) {
        return `<p class="mb-3 text-gray-300">${paragraph}</p>`;
      }
      return paragraph;
    }).join('\n\n');

    return formatted;
  };

  // Copy to clipboard
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(localValue);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // Download as file
  const downloadAsFile = () => {
    const blob = new Blob([localValue], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'app_spec.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`spec-editor ${className}`}>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3 p-3 bg-gray-900 border border-gray-800 rounded-t-lg">
        <div className="flex items-center gap-4">
          {/* Mode Toggle */}
          <div className="flex gap-1 p-0.5 bg-gray-950 rounded">
            <button
              type="button"
              onClick={() => setIsPreview(false)}
              className={`px-3 py-1 text-sm rounded transition-colors ${
                !isPreview
                  ? 'bg-gray-800 text-gray-200'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              disabled={disabled}
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => setIsPreview(true)}
              className={`px-3 py-1 text-sm rounded transition-colors ${
                isPreview
                  ? 'bg-gray-800 text-gray-200'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
              disabled={disabled}
            >
              Preview
            </button>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>{wordCount} words</span>
            <span>•</span>
            <span>{lineCount} lines</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {onValidate && (
            <button
              type="button"
              onClick={() => onValidate(localValue)}
              className="px-3 py-1 text-sm text-blue-400 hover:text-blue-300 transition-colors"
              disabled={disabled || !localValue.trim()}
            >
              Validate
            </button>
          )}
          <button
            type="button"
            onClick={copyToClipboard}
            className="px-3 py-1 text-sm text-gray-400 hover:text-gray-300 transition-colors"
            disabled={disabled || !localValue.trim()}
            title="Copy to clipboard"
          >
            📋 Copy
          </button>
          <button
            type="button"
            onClick={downloadAsFile}
            className="px-3 py-1 text-sm text-gray-400 hover:text-gray-300 transition-colors"
            disabled={disabled || !localValue.trim()}
            title="Download as file"
          >
            💾 Download
          </button>
        </div>
      </div>

      {/* Editor/Preview Area */}
      <div className="relative">
        {!isPreview ? (
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={localValue}
              onChange={handleChange}
              placeholder={placeholder}
              disabled={disabled}
              className="w-full min-h-[400px] p-4 bg-gray-950 border border-gray-800 rounded-b-lg text-gray-100 font-mono text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              style={{ fontFamily: 'Consolas, Monaco, "Courier New", monospace' }}
            />

            {/* Markdown hints */}
            <div className="absolute bottom-3 right-3 text-xs text-gray-600 pointer-events-none">
              <div>**bold** *italic* `code`</div>
              <div># Heading ## Subheading</div>
              <div>- List item</div>
            </div>
          </div>
        ) : (
          <div className="min-h-[400px] p-4 bg-gray-950 border border-gray-800 rounded-b-lg overflow-auto">
            {localValue.trim() ? (
              <div
                className="prose prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: formatMarkdown(localValue) }}
              />
            ) : (
              <p className="text-gray-600 italic">Nothing to preview yet...</p>
            )}
          </div>
        )}
      </div>

      {/* Help Text */}
      <div className="mt-3 p-3 bg-blue-950/20 border border-blue-900/30 rounded-lg">
        <div className="flex gap-2">
          <span className="text-blue-400 text-sm flex-shrink-0">💡</span>
          <div className="text-xs text-blue-300">
            <strong>Tip:</strong> A good specification includes:
            <span className="ml-2">• Project overview and goals</span>
            <span className="ml-2">• Key features and requirements</span>
            <span className="ml-2">• Technical stack preferences</span>
            <span className="ml-2">• UI/UX requirements</span>
            <span className="ml-2">• Data models and API endpoints</span>
          </div>
        </div>
      </div>
    </div>
  );
}