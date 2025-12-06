import axios from 'axios';
import { UploadedFile, SearchResponse } from './types';

const API_BASE_URL = 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

export const fileApi = {
  // Check upload status
  checkStatus: async (fileMd5: string) => {
    const response = await api.get<{ uploadedChunks: number[], status: string }>(`/upload/status`, {
      params: { file_md5: fileMd5 } // Backend expects snake_case? Check upload.py: file_md5
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
    const response = await api.post('/upload/merge', { file_md5: fileMd5, file_name: fileName });
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

  delete: async (fileMd5: string) => {
    await api.delete(`/documents/${fileMd5}`);
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
  sendMessage: async (message: string) => {
    // 调用真实的 Search API
    const searchRes = await searchApi.search(message, 5);
    
    // 根据搜索结果构建回复内容
    let content: string;
    
    if (searchRes.results.length === 0) {
      content = `No relevant information found for "${message}". Try uploading related documents first.`;
    } else {
      // 显示搜索统计信息 (Top result is always 100% in relative scoring)
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
