import React, { useState, useEffect, useCallback } from 'react';
import { NavLink, Outlet, useNavigate, useParams, useLocation } from 'react-router-dom';
import {
  MessageSquare,
  Database,
  Brain,
  BarChart3,
  Plus,
  Trash2,
  Pencil,
  ChevronLeft,
} from 'lucide-react';
import { clsx } from 'clsx';
import { conversationApi } from '../api';
import { Conversation } from '../types';

const Layout: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { conversationId } = useParams();

  const createConversationId = () =>
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `conv_${Date.now()}_${Math.random().toString(16).slice(2)}`;

  const isOnChatPage = location.pathname.startsWith('/chat');

  const loadConversations = useCallback(async () => {
    try {
      setLoadingConversations(true);
      const response = await conversationApi.listAll();
      if (response.data) {
        setConversations(response.data.filter((conversation) => conversation.message_count > 0));
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    const interval = setInterval(loadConversations, 30000);
    return () => clearInterval(interval);
  }, [loadConversations]);

  useEffect(() => {
    if (isOnChatPage) loadConversations();
  }, [location.pathname, loadConversations, isOnChatPage]);

  const createNewConversation = async () => {
    try {
      setCreatingConversation(true);
      const response = await conversationApi.create();
      const newId = response?.data?.conversation_id || createConversationId();
      await loadConversations();
      navigate(`/chat/${newId}`);
    } catch (error) {
      console.error('Failed to create conversation:', error);
      const fallbackId = createConversationId();
      navigate(`/chat/${fallbackId}`);
    } finally {
      setCreatingConversation(false);
    }
  };

  const renameConversation = async (convId: string, currentTitle: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const nextTitle = prompt('Rename chat', currentTitle)?.trim();
    if (!nextTitle || nextTitle === currentTitle) return;

    try {
      await conversationApi.rename(convId, nextTitle);
      setConversations((prev) =>
        prev.map((c) => (c.conversation_id === convId ? { ...c, title: nextTitle } : c))
      );
    } catch (error) {
      console.error('Failed to rename conversation:', error);
    }
  };

  const deleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!confirm('Are you sure you want to delete this conversation?')) return;

    try {
      await conversationApi.clearHistory(convId);
      setConversations((prev) => prev.filter((c) => c.conversation_id !== convId));

      if (convId === conversationId) createNewConversation();
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

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

  const AppTitle = 'AI Study Assistant';

  return (
    <div className="h-screen w-full bg-gradient-to-b from-neutral-100 to-white">
      <div className="h-full w-full max-w-[1400px] mx-auto p-3">
        <div className="h-full w-full bg-white/90 backdrop-blur rounded-3xl shadow-sm border border-neutral-200 overflow-hidden flex">
          {/* Sidebar */}
          <aside className="w-80 border-r border-neutral-200 bg-neutral-50/70 flex flex-col">
            {/* Sidebar top */}
            <div className="px-4 py-4 border-b border-neutral-200 bg-white/70">
              <div className="flex items-center gap-3">
                <button
                  className="p-2 rounded-xl hover:bg-neutral-100 transition-colors"
                  title="Back"
                  onClick={() => navigate(-1)}
                >
                  <ChevronLeft className="w-5 h-5 text-neutral-600" />
                </button>

                {/* Logo */}
                <div className="flex items-center gap-2">
                  <div className="bg-neutral-900 p-2 rounded-2xl shadow-sm">
                    <Brain className="w-5 h-5 text-white" />
                  </div>
                  <div className="leading-tight">
                    <div className="font-semibold text-neutral-900">{AppTitle}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Sidebar nav */}
            <div className="p-3">
              <div className="space-y-2">
                <NavLink
                  to="/files"
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl transition-all text-sm border',
                      isActive
                        ? 'bg-neutral-200 text-neutral-900 font-medium border-neutral-300'
                        : 'bg-white text-neutral-700 border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300'
                    )
                  }
                >
                  <Database className="w-5 h-5" />
                  Knowledge Base
                </NavLink>

                <NavLink
                  to="/quiz"
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl transition-all text-sm border',
                      isActive
                        ? 'bg-neutral-200 text-neutral-900 font-medium border-neutral-300'
                        : 'bg-white text-neutral-700 border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300'
                    )
                  }
                >
                  <Brain className="w-5 h-5" />
                  Quiz
                </NavLink>

                <NavLink
                  to="/evaluation"
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl transition-all text-sm border',
                      isActive
                        ? 'bg-neutral-200 text-neutral-900 font-medium border-neutral-300'
                        : 'bg-white text-neutral-700 border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300'
                    )
                  }
                >
                  <BarChart3 className="w-5 h-5" />
                  Evaluation
                </NavLink>
              </div>
            </div>

            {/* Chats */}
            <div className="flex-1 flex flex-col overflow-hidden border-t border-neutral-200">
              <div className="p-3 flex items-center justify-between">
                <NavLink
                  to="/chat"
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl transition-all text-sm flex-1 border',
                      isActive && !conversationId
                        ? 'bg-neutral-900 text-white font-medium border-neutral-900'
                        : 'bg-white text-neutral-700 border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300'
                    )
                  }
                >
                  <MessageSquare className="w-5 h-5" />
                  Chat
                </NavLink>

                <button
                  onClick={createNewConversation}
                  disabled={creatingConversation}
                  className="ml-2 inline-flex items-center justify-center p-2 rounded-2xl bg-white border border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300 transition-all"
                  title="New chat"
                >
                  <Plus className="w-5 h-5 text-neutral-700" />
                </button>
              </div>

              {/* Conversation list */}
              <div className="flex-1 overflow-y-auto px-3 pb-3">
                {loadingConversations && conversations.length === 0 ? (
                  <div className="text-center text-neutral-400 text-sm py-6">Loading...</div>
                ) : conversations.length === 0 ? (
                  <div className="text-center text-neutral-400 text-xs py-6">
                    No conversations yet
                  </div>
                ) : (
                  <div className="space-y-2">
                    {conversations.map((conv) => (
                      <NavLink
                        key={conv.conversation_id}
                        to={`/chat/${conv.conversation_id}`}
                        className={({ isActive }) =>
                          clsx(
                            'group flex items-start gap-3 px-3 py-3 rounded-2xl transition-all border',
                            isActive
                              ? 'bg-neutral-200 border-neutral-300'
                              : 'bg-white border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50'
                          )
                        }
                      >
                        <div className="mt-0.5 shrink-0 p-2 rounded-xl border border-neutral-200 bg-white">
                          <MessageSquare className="w-4 h-4 text-neutral-600" />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="truncate text-sm font-medium text-neutral-900">
                            {conv.title}
                          </div>

                          <div className="mt-1 flex items-center justify-between text-xs text-neutral-500">
                            <span className="truncate">{conv.message_count} msgs</span>
                            <span className="shrink-0 ml-2">
                              {formatTime(conv.last_message_time)}
                            </span>
                          </div>
                        </div>

                        <div className="shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                          <button
                            onClick={(e) => renameConversation(conv.conversation_id, conv.title, e)}
                            className="p-2 rounded-xl hover:bg-neutral-100"
                            title="Rename"
                          >
                            <Pencil className="w-4 h-4 text-neutral-600" />
                          </button>
                          <button
                            onClick={(e) => deleteConversation(conv.conversation_id, e)}
                            className="p-2 rounded-xl hover:bg-red-50"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Sidebar bottom */}
            <div className="px-4 pt-3 pb-4 border-t border-neutral-200 text-xs text-neutral-500 bg-white/70 leading-relaxed break-words">
              Tip: Upload files inside a chat to scope retrieval to that conversation.
            </div>
          </aside>

          {/* Main content wrapper */}
          <main className="flex-1 flex flex-col overflow-hidden">
            {/* Top header */}
            <header className="h-16 border-b border-neutral-200 bg-white/70 backdrop-blur flex items-center px-5">
              <div className="w-10" />
              <div className="flex-1 flex items-center justify-center gap-2">
                <div className="bg-neutral-50 border border-neutral-200 rounded-2xl px-3 py-1.5 flex items-center gap-2">
                  <Brain className="w-4 h-4 text-neutral-700" />
                  <div className="font-semibold text-neutral-900">{AppTitle}</div>
                </div>
              </div>

              <div className="w-10" />
            </header>

            {/* Page content */}
            <div className="flex-1 overflow-hidden">
              <Outlet context={{ refreshConversations: loadConversations }} />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
};

export default Layout;
