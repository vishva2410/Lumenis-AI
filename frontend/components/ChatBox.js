'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Send, Bot, User, Loader2, AlertCircle, WifiOff } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import './ChatBox.css';

/**
 * ChatBox — WebSocket-powered clinical assistant chat component.
 *
 * Connects to the backend streaming chat endpoint and renders
 * a polished, animated conversation UI with user / assistant / system messages.
 *
 * @param {{ jobId: string }} props
 */
export default function ChatBox({ jobId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connectionStatus, setConnectionStatus] = useState('connecting'); // 'connecting' | 'connected' | 'disconnected' | 'error'
  const [isReceiving, setIsReceiving] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;

  /* ── Auto-scroll ──────────────────────────────────── */
  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isReceiving, scrollToBottom]);

  /* ── WebSocket lifecycle ──────────────────────────── */
  useEffect(() => {
    if (!jobId) return;

    const connectWebSocket = () => {
      setConnectionStatus('connecting');
      setErrorMessage(null);

      // Build the WS URL — honour env override first
      const envWsUrl = process.env.NEXT_PUBLIC_WS_URL;
      const wsUrl = envWsUrl
        ? `${envWsUrl}/api/chat/ws/${jobId}`
        : `ws://localhost:8000/api/chat/ws/${jobId}`;

      const socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        setConnectionStatus('connected');
        setErrorMessage(null);
        reconnectAttempts.current = 0;
        setMessages(prev => {
          // Only add system message if the chat is fresh
          if (prev.length === 0) {
            return [
              {
                id: crypto.randomUUID(),
                role: 'system',
                content: 'Connected to Clinical Assistant. Ask any follow-up questions about the analysis.',
              },
            ];
          }
          return prev;
        });
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.event === 'connected') {
            // Already handled in onopen
            return;
          }

          if (data.event === 'error') {
            setErrorMessage(data.detail || 'An error occurred during processing.');
            setIsReceiving(false);
            return;
          }

          if (data.token) {
            setIsReceiving(true);
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];

              if (last && last.role === 'assistant' && last.isStreaming) {
                // Append token to the existing streaming message
                return updated.map((msg, i) =>
                  i === updated.length - 1
                    ? { ...msg, content: msg.content + data.token }
                    : msg
                );
              }

              // Start a new assistant message
              return [
                ...updated,
                {
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: data.token,
                  isStreaming: true,
                },
              ];
            });
          }

          if (data.event === 'done') {
            setIsReceiving(false);
            setMessages(prev =>
              prev.map((msg, i) =>
                i === prev.length - 1 && msg.role === 'assistant'
                  ? { ...msg, isStreaming: false }
                  : msg
              )
            );

            // Re-focus input after response completes
            setTimeout(() => inputRef.current?.focus(), 100);
          }
        } catch (err) {
          console.error('ChatBox: failed to parse WS message:', err);
        }
      };

      socket.onclose = (event) => {
        wsRef.current = null;

        if (event.code === 1000) {
          // Normal close — component unmounting
          setConnectionStatus('disconnected');
          return;
        }

        // Abnormal close — attempt reconnect
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current += 1;
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 8000);
          setTimeout(connectWebSocket, delay);
        } else {
          setConnectionStatus('error');
          setErrorMessage('Unable to connect. Please refresh the page to try again.');
        }
      };

      socket.onerror = () => {
        // onerror fires before onclose — let onclose handle reconnect logic
        setConnectionStatus('error');
      };

      wsRef.current = socket;
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounting');
        wsRef.current = null;
      }
    };
  }, [jobId]);

  /* ── Send message ─────────────────────────────────── */
  const sendMessage = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || !wsRef.current || isReceiving || connectionStatus !== 'connected') return;

    setMessages(prev => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: trimmed },
    ]);
    setInput('');
    setIsReceiving(true);

    wsRef.current.send(JSON.stringify({ message: trimmed }));
  };

  /* ── Format message content (basic markdown) ─────── */
  const formatContent = (content) => {
    if (!content) return '';
    const html = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
      .replace(/\n/g, '<br />');
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  /* ── Status helpers ───────────────────────────────── */
  const isInputDisabled = connectionStatus !== 'connected' || isReceiving;

  const renderStatus = () => {
    switch (connectionStatus) {
      case 'connecting':
        return (
          <span className="chatStatus connecting">
            <Loader2 size={12} className="spinner" />
            Connecting…
          </span>
        );
      case 'connected':
        return (
          <span className="chatStatus connected">
            <span className="statusDot" />
            Connected
          </span>
        );
      case 'error':
      case 'disconnected':
        return (
          <span className="chatStatus disconnected">
            <WifiOff size={12} />
            Disconnected
          </span>
        );
      default:
        return null;
    }
  };

  /* ── Render ────────────────────────────────────────── */
  return (
    <div className="chatContainer">
      {/* ── Header ──────────────────────────────────── */}
      <div className="chatHeader">
        <div className="chatTitle">
          <div className="chatTitleIcon">
            <Bot size={18} />
          </div>
          <h3>Clinical Assistant</h3>
        </div>
        {renderStatus()}
      </div>

      {/* ── Messages ────────────────────────────────── */}
      <div className="chatMessages">
        {errorMessage && (
          <motion.div
            className="chatError"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <AlertCircle size={15} />
            <span>{errorMessage}</span>
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              className={`messageWrapper ${msg.role}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            >
              {msg.role === 'assistant' && (
                <div className="messageAvatar assistantAvatar">
                  <Bot size={14} />
                </div>
              )}

              {msg.role === 'user' && (
                <div className="messageAvatar userAvatar">
                  <User size={14} />
                </div>
              )}

              <div className={`messageBubble ${msg.role}`}>
                {msg.role === 'system' ? (
                  <span>{msg.content}</span>
                ) : (
                  formatContent(msg.content)
                )}
                {msg.isStreaming && (
                  <span className="streamingCursor" />
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator while waiting for first token */}
        {isReceiving && messages[messages.length - 1]?.role === 'user' && (
          <motion.div
            className="messageWrapper assistant"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="messageAvatar assistantAvatar">
              <Bot size={14} />
            </div>
            <div className="messageBubble assistant">
              <span className="typingDots">
                <span />
                <span />
                <span />
              </span>
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input ───────────────────────────────────── */}
      <form className="chatInputArea" onSubmit={sendMessage}>
        <input
          ref={inputRef}
          type="text"
          className="chatInput"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            connectionStatus !== 'connected'
              ? 'Waiting for connection…'
              : 'Ask a question about the report…'
          }
          disabled={isInputDisabled}
        />
        <button
          type="submit"
          className="sendBtn"
          disabled={!input.trim() || isInputDisabled}
          aria-label="Send message"
        >
          {isReceiving ? <Loader2 size={18} className="spinner" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  );
}
