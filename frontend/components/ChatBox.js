'use client';

import { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, AlertCircle } from 'lucide-react';
import './ChatBox.css';

export default function ChatBox({ jobId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isConnecting, setIsConnecting] = useState(true);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const [isReceiving, setIsReceiving] = useState(false);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isReceiving]);

  useEffect(() => {
    if (!jobId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use localhost:8000 for local dev
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || `ws://localhost:8000/api/chat/ws/${jobId}`;
    
    const socket = new WebSocket(wsUrl);
    ws.current = socket;

    socket.onopen = () => {
      console.log('WebSocket connected');
      setIsConnecting(false);
      setError(null);
      setMessages([{ role: 'system', content: 'Chat connected. You can ask follow-up questions about the analysis.' }]);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.event === 'connected') {
          // Handled in onopen
        } else if (data.event === 'error') {
          setError(data.detail || 'An error occurred');
          setIsReceiving(false);
        } else if (data.token) {
          setIsReceiving(true);
          setMessages(prev => {
            const newMessages = [...prev];
            const last = newMessages[newMessages.length - 1];
            
            if (last && last.role === 'assistant' && last.isStreaming) {
              // Append to streaming message
              last.content += data.token;
            } else {
              // Create new streaming message
              newMessages.push({ role: 'assistant', content: data.token, isStreaming: true });
            }
            return newMessages;
          });
        } else if (data.event === 'done') {
          setIsReceiving(false);
          setMessages(prev => {
            const newMessages = [...prev];
            const last = newMessages[newMessages.length - 1];
            if (last && last.role === 'assistant') {
              last.isStreaming = false;
            }
            return newMessages;
          });
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    socket.onclose = (event) => {
      console.log('WebSocket disconnected:', event.code);
      setIsConnecting(false);
      if (event.code !== 1000) {
        setError('Chat disconnected. Please refresh to reconnect.');
      }
    };

    return () => {
      socket.close(1000, 'Component unmounting');
    };
  }, [jobId]);

  const sendMessage = (e) => {
    e.preventDefault();
    if (!input.trim() || !ws.current || isReceiving) return;

    const messageContent = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: messageContent }]);
    setInput('');
    setIsReceiving(true);
    
    ws.current.send(JSON.stringify({ message: messageContent }));
  };

  const renderMessageContent = (content) => {
    // Basic formatting: bold, italic, line breaks
    // In a real app, use a proper Markdown parser like react-markdown
    const formatted = content
      .replace(/\n/g, '<br />')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    return <div dangerouslySetInnerHTML={{ __html: formatted }} />;
  };

  return (
    <div className="chat-container glass-card">
      <div className="chat-header">
        <div className="chat-title">
          <Bot size={18} color="var(--accent-primary)" />
          <h3>Clinical Inquiry</h3>
        </div>
        {isConnecting && <span className="chat-status status-connecting"><Loader2 size={12} className="spinner" /> Connecting...</span>}
        {!isConnecting && !error && <span className="chat-status status-connected"><span className="status-dot status-completed"></span> Connected</span>}
      </div>

      <div className="chat-messages">
        {error && (
          <div className="chat-error">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        
        {messages.map((msg, index) => (
          <div key={index} className={`message-wrapper ${msg.role}`}>
            {msg.role !== 'system' && (
              <div className="message-avatar">
                {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </div>
            )}
            <div className={`message-bubble ${msg.role}`}>
              {msg.role === 'system' ? (
                <span>{msg.content}</span>
              ) : (
                renderMessageContent(msg.content)
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-area" onSubmit={sendMessage}>
        <input
          type="text"
          className="input-field"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about the report..."
          disabled={isConnecting || error || isReceiving}
        />
        <button 
          type="submit" 
          className="btn btn-primary send-btn"
          disabled={!input.trim() || isConnecting || error || isReceiving}
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
