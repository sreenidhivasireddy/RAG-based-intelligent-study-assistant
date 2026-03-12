import axios from 'axios';
import {
  UploadedFile,
  SearchResponse,
  QuizDifficulty,
  QuizBloomLevel,
  QuizResponse,
  EvalProvider,
  DatasetSource,
  RagEvaluationResponse,
  RagBatchDatasetItem,
  RagBatchEvaluationResponse,
  AutomatedEvalResponse,
  HealthResponse,
  EvaluationRegressionPoint,
} from './types';

const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1';
const DEFAULT_WS_BASE_URL = 'ws://localhost:8000/api/v1';
const DEFAULT_HEALTH_URL = 'http://localhost:8000/health';

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL
);

const WS_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_WS_BASE_URL ||
    API_BASE_URL.replace(/^http:\/\//, 'ws://').replace(/^https:\/\//, 'wss://')
);

const HEALTH_URL = trimTrailingSlash(
  import.meta.env.VITE_HEALTH_URL || DEFAULT_HEALTH_URL
);

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

export const fileApi = {
  // Check upload status
  checkStatus: async (fileMd5: string) => {
    const response = await api.get<{ code: number; message: string; data: { uploaded: number[]; progress: number; total_chunks: number } }>(`/upload/status`, {
      params: { file_md5: fileMd5 } // Backend expects snake_case
    });
    return response.data;
  },

  // Upload a single chunk
  uploadChunk: async (
    chunk: Blob,
    metadata: {
      fileMd5: string;
      chunkIndex: number;
      totalSize: number;
      fileName: string;
      totalChunks?: number;
    },
    onProgress?: (progress: number) => void,
    cancelSignal?: AbortSignal
  ) => {
    const formData = new FormData();
    formData.append('file', chunk);
    formData.append('fileMd5', metadata.fileMd5);
    formData.append('chunkIndex', metadata.chunkIndex.toString());
    formData.append('totalSize', metadata.totalSize.toString());
    formData.append('fileName', metadata.fileName);
    if (metadata.totalChunks) {
      formData.append('totalChunks', metadata.totalChunks.toString());
    }

    const response = await api.post('/upload/chunk', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal: cancelSignal,
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percentCompleted);
        }
      },
    });
    return response.data;
  },

  // Merge chunks
  merge: async (fileMd5: string, fileName: string) => {
    // Backend expects snake_case for merge request
    const response = await api.post<{ code: number; message: string; data: { object_url: string; file_size: number } }>('/upload/merge', { file_md5: fileMd5, file_name: fileName });
    return response.data;
  },

  upload: async (file: File, onProgress?: (progress: number) => void) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<UploadedFile>('/upload/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
            if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
        }
    });
    return response.data;
  },

  list: async () => {
    // Updated endpoint - returns { status: "success", data: [...] }
    const response = await api.get<{ status: string, data: UploadedFile[] }>('/documents/uploads');
    return response.data.data;
  },

  getOpenUrl: async (fileMd5: string) => {
    const response = await api.get<{
      code: number;
      message: string;
      data: { fileMd5: string; fileName: string; url: string; blobPath: string };
    }>(`/documents/${fileMd5}/open-url`);
    return response.data.data.url;
  },

  delete: async (fileMd5: string) => {
    await api.delete(`/documents/${fileMd5}`);
  },

  getContent: async (fileMd5: string) => {
    const response = await api.get<{
      code: number;
      message: string;
      data: {
        fileMd5: string;
        fileName: string;
        content: string;
        contentLength: number;
        contentTruncated: boolean;
      } | null;
    }>(`/documents/${fileMd5}/content`);
    return response.data.data;
  }
};

export const searchApi = {
  search: async (query: string, topK: number = 5) => {
    const response = await api.post<SearchResponse>('/search/', {
      query,
      top_k: topK,
      search_mode: 'hybrid',
      auto_adjust: true
    });
    return response.data;
  }
};

export const chatApi = {
  // WebSocket chat - real-time streaming response
  createWebSocket: (conversationId: string) => {
    const wsUrl = `${WS_BASE_URL}/chat/ws/${conversationId}`;
    return new WebSocket(wsUrl);
  },

  // Send a message through WebSocket
  sendMessageViaWebSocket: (ws: WebSocket, message: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message }));
    } else {
      throw new Error('WebSocket is not connected');
    }
  },

  // Fallback: non-streaming chat using the search API
  sendMessage: async (message: string) => {
    // Call the real search API
    const searchRes = await searchApi.search(message, 5);
    
    // Build the response from search results
    let content: string;
    
    if (searchRes.results.length === 0) {
      content = `No relevant information found for "${message}". Try uploading related documents first.`;
    } else {
      // Show search statistics (top result is always 100% in relative scoring)
      const topResult = searchRes.results[0];
      const sourceInfo = topResult.file_name ? `📄 **Source:** ${topResult.file_name}\n` : '';
      content = `Found ${searchRes.total_results} relevant result(s) in ${searchRes.execution_time_ms?.toFixed(0) || 0}ms.\n\n` +
        `**Search Mode:** ${searchRes.search_mode}\n` +
        sourceInfo +
        `**Top Match (Score: ${(topResult.score * 100).toFixed(1)}%):**\n\n` +
        `"${topResult.text_content.substring(0, 300)}${topResult.text_content.length > 300 ? '...' : ''}"`;
    }
    
    return {
      content: content,
      sources: searchRes.results,
      searchResponse: searchRes
    };
  }
};

export const quizApi = {
  generate: async (payload: {
    topic: string;
    difficulty: QuizDifficulty;
    number_of_questions: number;
    bloom_level: QuizBloomLevel;
    retrieved_chunks: string[];
  }) => {
    const response = await api.post<QuizResponse>('/quiz/generate', payload);
    return response.data;
  }
};

export const evaluationApi = {
  runEvaluationPipeline: async (payload?: { mode?: DatasetSource; dataset_source?: DatasetSource }) => {
    const response = await api.post<AutomatedEvalResponse>('/evaluate/run', payload ?? {}, {
      timeout: 600000,
    });
    return response.data;
  },

  getHistory: async (datasetSource: DatasetSource = 'fixed', limit: number = 20) => {
    const response = await api.get<EvaluationRegressionPoint[]>('/evaluate/history', {
      params: {
        dataset_source: datasetSource,
        limit,
      },
    });
    return response.data;
  },

  evaluateRag: async (payload: {
    question: string;
    answer: string;
    retrieved_chunks: string[];
    reference_answer?: string;
    provider?: EvalProvider;
  }) => {
    const response = await api.post<RagEvaluationResponse>('/evaluation/rag', payload);
    return response.data;
  },

  evaluateRagBatch: async (payload: {
    dataset: RagBatchDatasetItem[];
    provider?: 'azure_ai_evaluation';
    top_k?: number;
    file_md5_filter?: string;
  }) => {
    const response = await api.post<RagBatchEvaluationResponse>('/evaluation/rag/batch', {
      provider: 'azure_ai_evaluation',
      ...payload,
    });
    return response.data;
  }
};

// Conversation API
export const conversationApi = {
  create: async (conversationId?: string) => {
    const response = await api.post<{
      code: number;
      message: string;
      data: {
        conversation_id: string;
        title: string;
        message_count: number;
        first_message_time: string | null;
        last_message_time: string | null;
        preview: string;
      };
    }>('/conversations/', null, {
      params: conversationId ? { conversation_id: conversationId } : undefined
    });

    return response.data;
  },

  rename: async (conversationId: string, title: string) => {
    const response = await api.patch(`/conversations/${conversationId}/title`, { title });
    return response.data;
  },

  // Get all conversations
  listAll: async () => {
    const response = await api.get<{
      code: number;
      message: string;
      data: Array<{
        conversation_id: string;
        title: string;
        message_count: number;
        first_message_time: string | null;
        last_message_time: string | null;
        preview: string;
      }>;
    }>('/conversations/');
    
    return response.data;
  },

  // Get conversation history
  getHistory: async (conversationId: string, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    const response = await api.get<{
      code: number;
      message: string;
      data: Array<{
        role: 'user' | 'assistant';
        content: string;
        timestamp: string;
      }>;
    }>(`/conversations/${conversationId}?${params}`);
    
    return response.data;
  },

  // Clear conversation history
  clearHistory: async (conversationId: string) => {
    const response = await api.delete(`/conversations/${conversationId}`);
    return response.data;
  },

  // Get conversation summary
  getSummary: async (conversationId: string) => {
    const response = await api.get(`/conversations/${conversationId}/summary`);
    return response.data;
  },

  attachFile: async (conversationId: string, fileMd5: string, fileName: string) => {
    const response = await api.post(`/conversations/${conversationId}/files`, {
      file_md5: fileMd5,
      file_name: fileName,
    });
    return response.data;
  },
};

export const systemApi = {
  health: async () => {
    const response = await axios.get<HealthResponse>(HEALTH_URL);
    return response.data;
  }
};
