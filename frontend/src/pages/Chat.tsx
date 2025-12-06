import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, User, Bot, Book, ChevronRight, ChevronDown } from 'lucide-react';
import { useParams, useOutletContext } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { chatApi, conversationApi } from '../api';
import { ChatMessage, SearchResult } from '../types';
import { clsx } from 'clsx';

interface LayoutContext {
  refreshConversations: () => void;
}

const Chat: React.FC = () => {
  const { conversationId: urlConversationId } = useParams();
  const { refreshConversations } = useOutletContext<LayoutContext>();
  
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello! I am your AI study assistant. Ask me anything about your uploaded documents.',
      timestamp: Date.now()
    }
  ]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(() => urlConversationId || `conv_${Date.now()}`);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const currentMessageRef = useRef<string>('');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 当 URL 参数变化时更新会话 ID
  useEffect(() => {
    if (urlConversationId && urlConversationId !== conversationId) {
      setConversationId(urlConversationId);
    }
  }, [urlConversationId, conversationId]);

  // 加载历史会话
  const loadConversationHistory = useCallback(async (convId: string) => {
    try {
      const response = await conversationApi.getHistory(convId);
      if (response.data && response.data.length > 0) {
        const loadedMessages: ChatMessage[] = response.data.map((msg, idx) => ({
          id: `${convId}-${idx}`,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp ? new Date(msg.timestamp).getTime() : Date.now()
        }));
        setMessages(loadedMessages);
      } else {
        setMessages([{
          id: 'welcome',
          role: 'assistant',
          content: 'Hello! I am your AI study assistant. Ask me anything about your uploaded documents.',
          timestamp: Date.now()
        }]);
      }
    } catch (error) {
      console.error('Failed to load conversation history:', error);
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: 'Hello! I am your AI study assistant. Ask me anything about your uploaded documents.',
        timestamp: Date.now()
      }]);
    }
  }, []);

  // WebSocket 连接管理
  useEffect(() => {
    // 关闭旧连接
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close();
    }

    // 如果有 URL 参数，加载历史
    if (urlConversationId) {
      loadConversationHistory(urlConversationId);
    }

    // 创建新 WebSocket 连接
    const ws = chatApi.createWebSocket(conversationId);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('✅ WebSocket connected:', conversationId);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.error) {
          console.error('❌ Error from server:', data.error);
          setMessages(prev => [...prev, {
            id: Date.now().toString(),
            role: 'assistant',
            content: `Error: ${data.error}`,
            timestamp: Date.now()
          }]);
          setLoading(false);
          return;
        }

        if (data.chunk) {
          currentMessageRef.current += data.chunk;
          
          setMessages(prev => {
            const newMessages = [...prev];
            const lastMsg = newMessages[newMessages.length - 1];
            
            if (lastMsg && lastMsg.role === 'assistant' && lastMsg.id === 'streaming') {
              lastMsg.content = currentMessageRef.current;
            } else {
              newMessages.push({
                id: 'streaming',
                role: 'assistant',
                content: currentMessageRef.current,
                timestamp: Date.now()
              });
            }
            
            return newMessages;
          });
        }

        if (data.type === 'completion' && data.status === 'finished') {
          console.log('✅ Response completed', data.source_files);
          setMessages(prev => {
            const newMessages = [...prev];
            const lastMsg = newMessages[newMessages.length - 1];
            
            if (lastMsg && lastMsg.id === 'streaming') {
              lastMsg.id = Date.now().toString();
              // 添加源文件列表
              if (data.source_files && data.source_files.length > 0) {
                lastMsg.source_files = data.source_files;
              }
            }
            
            return newMessages;
          });
          
          currentMessageRef.current = '';
          setLoading(false);
          
          // 刷新会话列表
          refreshConversations?.();
        }
      } catch (error) {
        console.error('❌ Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
      setLoading(false);
    };

    ws.onclose = () => {
      console.log('🔌 WebSocket disconnected');
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [conversationId, urlConversationId, loadConversationHistory, refreshConversations]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    currentMessageRef.current = '';

    try {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        chatApi.sendMessageViaWebSocket(wsRef.current, userMsg.content);
      } else {
        throw new Error('WebSocket not connected');
      }
    } catch (error) {
      console.error('❌ Failed to send message:', error);
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please check the connection.',
        timestamp: Date.now()
      }]);
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <header className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-white z-10">
        <h2 className="font-semibold text-gray-800 flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-600" />
          AI Assistant
        </h2>
        <div className="text-xs text-gray-400">
          {messages.length > 1 ? `${messages.length} messages` : 'New conversation'}
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gray-50">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={clsx(
              "flex gap-4 max-w-4xl mx-auto",
              msg.role === 'user' ? "flex-row-reverse" : "flex-row"
            )}
          >
            {/* Avatar */}
            <div className={clsx(
              "w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm",
              msg.role === 'user' ? "bg-gray-800" : "bg-blue-600"
            )}>
              {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
            </div>

            {/* Content */}
            <div className={clsx(
              "flex flex-col gap-2 max-w-[80%]",
              msg.role === 'user' ? "items-end" : "items-start"
            )}>
              <div className={clsx(
                "p-4 rounded-2xl shadow-sm text-sm leading-relaxed",
                msg.role === 'user' 
                  ? "bg-gray-800 text-white rounded-tr-none whitespace-pre-wrap" 
                  : "bg-white text-gray-800 border border-gray-100 rounded-tl-none prose prose-sm max-w-none"
              )}>
                {msg.role === 'assistant' ? (
                  <ReactMarkdown
                    components={{
                      code: ({ node, className, children, ...props }) => {
                        const isInline = !className;
                        return isInline ? (
                          <code className="bg-gray-100 text-pink-600 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                            {children}
                          </code>
                        ) : (
                          <code className="block bg-gray-900 text-gray-100 p-3 rounded-lg text-xs font-mono overflow-x-auto" {...props}>
                            {children}
                          </code>
                        );
                      },
                      ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>,
                      h1: ({ children }) => <h1 className="text-lg font-bold mt-3 mb-2">{children}</h1>,
                      h2: ({ children }) => <h2 className="text-base font-bold mt-3 mb-2">{children}</h2>,
                      h3: ({ children }) => <h3 className="text-sm font-bold mt-2 mb-1">{children}</h3>,
                      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                      a: ({ href, children }) => (
                        <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                ) : (
                  msg.content
                )}
              </div>

              {/* RAG Source Files */}
              {msg.source_files && msg.source_files.length > 0 && (
                <div className="w-full mt-2">
                  <SourceFilesList files={msg.source_files} />
                </div>
              )}
              
              {/* RAG Sources (detailed) */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="w-full mt-2">
                  <SourcesAccordion sources={msg.sources} />
                </div>
              )}
              
              <span className="text-xs text-gray-400 px-1">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        ))}
        {loading && messages[messages.length - 1]?.id !== 'streaming' && (
          <div className="flex gap-4 max-w-4xl mx-auto">
            <div className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div className="flex items-center gap-1 bg-white px-4 py-3 rounded-2xl rounded-tl-none border border-gray-100">
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-200">
        <div className="max-w-4xl mx-auto relative">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Ask a question about your documents..."
            className="w-full bg-gray-50 border border-gray-300 rounded-xl pl-4 pr-14 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-none min-h-[52px] max-h-32"
            rows={1}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="absolute right-2 bottom-2 p-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white rounded-lg transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="text-center text-xs text-gray-400 mt-2">
          <p>AI can make mistakes. Check important info.</p>
        </div>
      </div>
    </div>
  );
};

// Component to display source files list
const SourceFilesList = ({ files }: { files: string[] }) => {
  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <div className="p-3 bg-gray-50">
        <div className="flex items-center gap-2 text-xs font-medium text-gray-600">
          <Book className="w-4 h-4 text-blue-500" />
          <span>Sources: {files.length} file{files.length > 1 ? 's' : ''} used</span>
        </div>
      </div>
      <div className="p-3 pt-2">
        <div className="flex flex-wrap gap-2">
          {files.map((file, idx) => (
            <span
              key={idx}
              className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded border border-blue-200 flex items-center gap-1"
            >
              <Book className="w-3 h-3" />
              {file}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

// Component to display RAG sources
const SourcesAccordion = ({ sources }: { sources: SearchResult[] }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2 text-xs font-medium text-gray-600">
          <Book className="w-4 h-4 text-blue-500" />
          {sources.length} References Found
        </div>
        {isOpen ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
      </button>
      
      {isOpen && (
        <div className="divide-y divide-gray-100">
          {sources.map((source, idx) => (
            <div key={`${source.file_md5}-${source.chunk_id}`} className="p-3 hover:bg-gray-50">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-gray-700">Source {idx + 1}</span>
                  {source.file_name && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded flex items-center gap-1">
                      📄 {source.file_name}
                    </span>
                  )}
                </div>
                <span className="text-[10px] px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                  {(source.score * 100).toFixed(1)}% Match
                </span>
              </div>
              <p 
                className="text-xs text-gray-600 leading-relaxed"
                dangerouslySetInnerHTML={{ 
                  __html: source.highlights && source.highlights.length > 0 
                    ? source.highlights[0]
                    : source.text_content.substring(0, 150) + "..." 
                }} 
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Chat;
