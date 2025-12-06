import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { MessageSquare, Database, BookOpen } from 'lucide-react';
import { clsx } from 'clsx';

const Layout: React.FC = () => {
  return (
    <div className="flex h-screen w-full bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 flex items-center gap-3 border-b border-gray-100">
          <div className="bg-blue-600 p-2 rounded-lg">
            <BookOpen className="w-6 h-6 text-white" />
          </div>
          <span className="font-bold text-xl text-gray-800">Study Assistant</span>
        </div>

        <nav className="flex-1 p-4 space-y-2">
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

          <NavLink
            to="/chat"
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-all",
                isActive
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )
            }
          >
            <MessageSquare className="w-5 h-5" />
            Chat
          </NavLink>
        </nav>

        <div className="p-4 border-t border-gray-100 text-xs text-gray-400 text-center">
          RAG System v1.0
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden flex flex-col relative">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;

