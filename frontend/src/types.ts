export interface UploadedFile {
  fileMd5: string;
  fileName: string;
  totalSize: number;
  status: number; // 0=uploading, 2=merged, 1=completed
  createdAt: string;
  mergedAt?: string;
  // Optional legacy fields if needed during transition, but better to remove
}

export interface SearchResult {
  file_md5: string;
  file_name?: string;  // Source file name
  chunk_id: number;
  text_content: string;
  score: number;
  highlights: string[];
  model_version?: string;
}

export interface SearchResponse {
  query: string;
  total_results: number;
  results: SearchResult[];
  search_mode: string;
  execution_time_ms: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SearchResult[]; // RAG 特性：回答引用的来源
  timestamp: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  updated_at: number;
}

export interface Conversation {
  conversation_id: string;
  title: string;
  message_count: number;
  first_message_time: string | null;
  last_message_time: string | null;
  preview: string;
}
