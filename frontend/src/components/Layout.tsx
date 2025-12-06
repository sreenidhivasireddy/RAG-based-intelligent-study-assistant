import React, { useState, useEffect, useCallback } from 'react';
import { NavLink, Outlet, useNavigate, useParams, useLocation } from 'react-router-dom';
import { MessageSquare, Database, BookOpen, Plus, Trash2 } from 'lucide-react';
import { clsx } from 'clsx';
import { conversationApi } from '../api';
import { Conversation } from '../types';

const Layout: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { conversationId } = useParams();
  
  const isOnChatPage = location.pathname.startsWith('/chat');

  // 加载会话列表
  const loadConversations = useCallback(async () => {
    try {
      setLoadingConversations(true);
      const response = await conversationApi.listAll();
      if (response.data) {
        setConversations(response.data);
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  // 初始加载和定期刷新
  useEffect(() => {
    loadConversations();
    
    // 每30秒刷新一次
    const interval = setInterval(loadConversations, 30000);
    return () => clearInterval(interval);
  }, [loadConversations]);

  // 监听路由变化刷新列表
  useEffect(() => {
    if (isOnChatPage) {
      loadConversations();
    }
  }, [location.pathname, loadConversations, isOnChatPage]);

  // 新建会话
  const createNewConversation = () => {
    const newId = `conv_${Date.now()}`;
    navigate(`/chat/${newId}`);
  };

  // 删除会话
  const deleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    
    try {
      await conversationApi.clearHistory(convId);
      setConversations(prev => prev.filter(c => c.conversation_id !== convId));
      
      // 如果删除的是当前会话，跳转到新会话
      if (convId === conversationId) {
        createNewConversation();
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  // 格式化时间
  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
      
      if (diffDays === 0) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      } else if (diffDays === 1) {
        return 'Yesterday';
      } else if (diffDays < 7) {
        return date.toLocaleDateString([], { weekday: 'short' });
      } else {
        return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
      }
    } catch {
      return '';
    }
  };

  return (
    <div className="flex h-screen w-full bg-gray-50">
      {/* Sidebar */}
      <aside className="w-72 bg-white border-r border-gray-200 flex flex-col">
        {/* Logo */}
        <div className="p-4 flex items-center gap-3 border-b border-gray-100">
          <div className="bg-blue-600 p-2 rounded-lg">
            <BookOpen className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-lg text-gray-800">Study Assistant</span>
        </div>

        <nav className="flex-1 flex flex-col overflow-hidden">
          {/* Knowledge Base Link */}
          <div className="p-3">
            <NavLink
              to="/files"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-all",
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                )
              }
            >
              <Database className="w-5 h-5" />
              Knowledge Base
            </NavLink>
          </div>

          {/* Chat Section */}
          <div className="flex-1 flex flex-col overflow-hidden border-t border-gray-100">
            {/* Chat Header with New Button */}
            <div className="p-3 flex items-center justify-between">
              <NavLink
                to="/chat"
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-4 py-3 rounded-lg transition-all flex-1",
                    isActive && !conversationId
                      ? "bg-blue-50 text-blue-700 font-medium"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  )
                }
              >
                <MessageSquare className="w-5 h-5" />
                Chat
              </NavLink>
              <button
                onClick={createNewConversation}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors ml-2"
                title="New conversation"
              >
                <Plus className="w-5 h-5 text-gray-600" />
              </button>
            </div>

            {/* Conversation List */}
            <div className="flex-1 overflow-y-auto px-3 pb-3">
              {loadingConversations && conversations.length === 0 ? (
                <div className="text-center text-gray-400 text-sm py-4">Loading...</div>
              ) : conversations.length === 0 ? (
                <div className="text-center text-gray-400 text-xs py-4">
                  No conversations yet
                </div>
              ) : (
                <div className="space-y-1">
                  {conversations.map((conv) => (
                    <NavLink
                      key={conv.conversation_id}
                      to={`/chat/${conv.conversation_id}`}
                      className={({ isActive }) =>
                        clsx(
                          "group flex items-center gap-2 px-3 py-2 rounded-lg transition-all text-sm",
                          isActive
                            ? "bg-blue-50 text-blue-700"
                            : "text-gray-600 hover:bg-gray-50"
                        )
                      }
                    >
                      <MessageSquare className="w-4 h-4 shrink-0 opacity-50" />
                      <div className="flex-1 min-w-0">
                        <div className="truncate font-medium text-sm">
                          {conv.title}
                        </div>
                        <div className="flex items-center justify-between text-xs text-gray-400 mt-0.5">
                          <span className="truncate">{conv.message_count} msgs</span>
                          <span className="shrink-0 ml-2">{formatTime(conv.last_message_time)}</span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => deleteConversation(conv.conversation_id, e)}
                        className="p-1 opacity-0 group-hover:opacity-100 hover:bg-red-100 rounded transition-all shrink-0"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </button>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          </div>
        </nav>

        <div className="p-3 border-t border-gray-100 text-xs text-gray-400 text-center">
          RAG System v1.0
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden flex flex-col relative">
        <Outlet context={{ refreshConversations: loadConversations }} />
      </main>
    </div>
  );
};

export default Layout;
