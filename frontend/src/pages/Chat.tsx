import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Book, ChevronRight, ChevronDown } from 'lucide-react';
import { chatApi } from '../api';
import { ChatMessage, SearchResult } from '../types';
import { clsx } from 'clsx';

const Chat: React.FC = () => {
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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

    try {
      const response = await chatApi.sendMessage(userMsg.content);
      
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.content, // 在真实 RAG 中，这里是 LLM 生成的回答
        sources: response.sources, // 搜索到的相关片段
        timestamp: Date.now()
      };

      setMessages(prev => [...prev, aiMsg]);
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error while searching.',
        timestamp: Date.now()
      }]);
    } finally {
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
                "p-4 rounded-2xl shadow-sm text-sm leading-relaxed whitespace-pre-wrap",
                msg.role === 'user' 
                  ? "bg-gray-800 text-white rounded-tr-none" 
                  : "bg-white text-gray-800 border border-gray-100 rounded-tl-none"
              )}>
                {msg.content}
              </div>

              {/* RAG Sources (Only for assistant) */}
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
        {loading && (
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
      <div className="p-6 bg-white border-t border-gray-200">
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
        <div className="text-center text-xs text-gray-400 mt-2 space-y-1">
          <p className="text-gray-500">
            💡 <span className="font-medium">Tip:</span> Use precise keywords for better results. 
            Avoid filler words like "tell me about" or "what is".
          </p>
          <p>AI can make mistakes. Check important info.</p>
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
                    ? source.highlights[0] // 使用高亮片段
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

