import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Loader2,
  XCircle,
  PauseCircle,
  PlayCircle,
  Search,
  Trash2,
} from 'lucide-react';
import { fileApi } from '../api';
import { UploadedFile } from '../types';
import { clsx } from 'clsx';
import SparkMD5 from 'spark-md5';
import { nanoid } from 'nanoid';

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
const MAX_CONCURRENT_UPLOADS = 3;

type FileType = 'ALL' | 'PDF' | 'DOCX' | 'TXT' | 'OTHER';

const TYPE_ORDER: Record<Exclude<FileType, 'ALL'>, number> = {
  PDF: 0,
  DOCX: 1,
  TXT: 2,
  OTHER: 3,
};

interface UploadTask {
  id: string;
  file: File;
  fileMd5?: string;
  fileName: string;
  totalSize: number;
  chunkIndex: number;
  totalChunks: number;
  uploadedChunks: number[];
  progress: number;
  status: 'pending' | 'hashing' | 'uploading' | 'merging' | 'completed' | 'error' | 'paused';
  error?: string;
  abortController?: AbortController;
}

const KnowledgeBase: React.FC = () => {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploadTasks, setUploadTasks] = useState<UploadTask[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const activeUploadsCount = useRef(0);

  // ✅ new: filter + search
  const [activeType, setActiveType] = useState<FileType>('ALL');
  const [query, setQuery] = useState('');
  const [deletingMd5, setDeletingMd5] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    try {
      const list = await fileApi.list();
      setFiles(list);
    } catch (error) {
      console.error('Failed to load files', error);
    }
  }, []);

  useEffect(() => {
    loadFiles();
    const interval = setInterval(loadFiles, 5000);
    return () => clearInterval(interval);
  }, [loadFiles]);

  // Process Queue Loop
  useEffect(() => {
    const processQueue = async () => {
      if (activeUploadsCount.current >= MAX_CONCURRENT_UPLOADS) return;

      const pendingTask = uploadTasks.find((t) => t.status === 'pending');
      if (pendingTask) startUpload(pendingTask.id);
    };

    processQueue();
  }, [uploadTasks]);

  const calculateMD5 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const blobSlice =
        File.prototype.slice ||
        (File.prototype as any).mozSlice ||
        (File.prototype as any).webkitSlice;

      const chunks = Math.ceil(file.size / CHUNK_SIZE);
      let currentChunk = 0;
      const spark = new SparkMD5.ArrayBuffer();
      const fileReader = new FileReader();

      fileReader.onload = function (e) {
        if (e.target?.result) spark.append(e.target.result as ArrayBuffer);
        currentChunk++;
        if (currentChunk < chunks) loadNext();
        else resolve(spark.end());
      };

      fileReader.onerror = function () {
        reject('MD5 calculation failed');
      };

      function loadNext() {
        const start = currentChunk * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        fileReader.readAsArrayBuffer(blobSlice.call(file, start, end));
      }

      loadNext();
    });
  };

  const updateTask = (id: string, updates: Partial<UploadTask>) => {
    setUploadTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...updates } : t)));
  };

  const startUpload = async (taskId: string) => {
    const task = uploadTasks.find((t) => t.id === taskId);
    if (!task) return;

    activeUploadsCount.current++;
    updateTask(taskId, { status: 'hashing' });

    try {
      // 1) MD5
      const fileMd5 = await calculateMD5(task.file);
      updateTask(taskId, { fileMd5 });

      // 2) Fast path if file exists
      const existingFile = files.find((f) => f.fileMd5 === fileMd5);
      if (existingFile) {
        updateTask(taskId, { status: 'completed', progress: 100 });
        activeUploadsCount.current--;
        setTimeout(() => setUploadTasks((prev) => prev.filter((t) => t.id !== taskId)), 1500);
        return;
      }

      // 3) Resume status
      let uploadedChunks: number[] = [];
      try {
        const status = await fileApi.checkStatus(fileMd5);
        if (status?.data) uploadedChunks = status.data.uploaded || [];
      } catch {
        // ignore
      }

      updateTask(taskId, { status: 'uploading', uploadedChunks });

      // 4) Upload chunks
      const abortController = new AbortController();
      updateTask(taskId, { abortController });

      const totalChunks = Math.ceil(task.file.size / CHUNK_SIZE);

      for (let i = 0; i < totalChunks; i++) {
        if (abortController.signal.aborted) throw new Error('Cancelled');
        if (uploadedChunks.includes(i)) continue;

        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, task.file.size);
        const chunk = task.file.slice(start, end);

        await fileApi.uploadChunk(
          chunk,
          {
            fileMd5,
            chunkIndex: i,
            totalSize: task.file.size,
            fileName: task.file.name,
            totalChunks,
          },
          () => {},
          abortController.signal
        );

        uploadedChunks.push(i);
        const progress = Math.round((uploadedChunks.length / totalChunks) * 100);
        updateTask(taskId, { uploadedChunks, progress });
      }

      // 5) Merge
      updateTask(taskId, { status: 'merging' });
      await fileApi.merge(fileMd5, task.file.name);

      updateTask(taskId, { status: 'completed', progress: 100 });
      loadFiles();

      setTimeout(() => setUploadTasks((prev) => prev.filter((t) => t.id !== taskId)), 1500);
    } catch (error: any) {
      if (error.message === 'Cancelled' || error.name === 'AbortError') {
        updateTask(taskId, { status: 'paused' });
      } else {
        console.error('Upload error:', error);
        updateTask(taskId, { status: 'error', error: error.message || 'Upload failed' });
      }
    } finally {
      activeUploadsCount.current--;
      setUploadTasks((prev) => [...prev]);
    }
  };

  const handleFileSelect = (file: File) => {
    const newTask: UploadTask = {
      id: nanoid(),
      file,
      fileName: file.name,
      totalSize: file.size,
      chunkIndex: 0,
      totalChunks: Math.ceil(file.size / CHUNK_SIZE),
      uploadedChunks: [],
      progress: 0,
      status: 'pending',
    };
    setUploadTasks((prev) => [...prev, newTask]);
  };

  const handleCancel = async (task: UploadTask) => {
    task.abortController?.abort();

    if (task.fileMd5) {
      try {
        await fileApi.delete(task.fileMd5);
      } catch (error: any) {
        if (error?.response?.status !== 404) {
          console.warn(`Failed to delete backend upload data for ${task.fileMd5}`, error);
        }
      }
    }

    setUploadTasks((prev) => prev.filter((t) => t.id !== task.id));
    await loadFiles();
  };

  const handlePause = (task: UploadTask) => {
    task.abortController?.abort();
    updateTask(task.id, { status: 'paused', abortController: undefined });
  };

  const handleResume = (task: UploadTask) => {
    updateTask(task.id, { status: 'pending' });
  };

  const handleOpenFile = async (file: UploadedFile) => {
    try {
      const url = await fileApi.getOpenUrl(file.fileMd5);
      if (url) {
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    } catch (error) {
      console.error('Failed to open file', error);
      alert('Unable to open file right now.');
    }
  };

  const handleDeleteFile = async (file: UploadedFile) => {
    if (!confirm(`Delete "${file.fileName}"? This will remove stored file data.`)) return;
    try {
      setDeletingMd5(file.fileMd5);
      await fileApi.delete(file.fileMd5);
      await loadFiles();
    } catch (error) {
      console.error('Failed to delete file', error);
      alert('Failed to delete file.');
    } finally {
      setDeletingMd5(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      Array.from(e.dataTransfer.files).forEach(handleFileSelect);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatTime = (dateString?: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60 * 1000) return 'Just now';
    if (diff < 60 * 60 * 1000) {
      const minutes = Math.floor(diff / (60 * 1000));
      return `${minutes} min ago`;
    }
    if (diff < 24 * 60 * 60 * 1000) {
      const hours = Math.floor(diff / (60 * 60 * 1000));
      return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    }

    const month = date.toLocaleDateString('en-US', { month: 'short' });
    const day = date.getDate();
    const year = date.getFullYear();
    const time = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    return `${month} ${day}, ${time}, ${year}`;
  };

  // -------------------------
  // ✅ File type helpers
  // -------------------------
  const getFileType = (fileName?: string): Exclude<FileType, 'ALL'> => {
    const name = (fileName || '').trim().toLowerCase();
    const ext = name.includes('.') ? name.split('.').pop() : '';
    if (ext === 'pdf') return 'PDF';
    if (ext === 'docx') return 'DOCX';
    if (ext === 'txt') return 'TXT';
    return 'OTHER';
  };

  const matchesQuery = (file: UploadedFile, q: string) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return (file.fileName || '').toLowerCase().includes(needle) || (file.fileMd5 || '').toLowerCase().includes(needle);
  };

  // ✅ Sorted & filtered list
  const visibleFiles = useMemo(() => {
    const filtered = files
      .filter((f) => matchesQuery(f, query))
      .filter((f) => {
        if (activeType === 'ALL') return true;
        return getFileType(f.fileName) === activeType;
      });

    // sort: by type order, then createdAt desc, then name asc
    const sorted = [...filtered].sort((a, b) => {
      const ta = getFileType(a.fileName);
      const tb = getFileType(b.fileName);

      const oa = TYPE_ORDER[ta];
      const ob = TYPE_ORDER[tb];
      if (oa !== ob) return oa - ob;

      const da = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const db = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      if (da !== db) return db - da;

      const na = (a.fileName || '').toLowerCase();
      const nb = (b.fileName || '').toLowerCase();
      return na.localeCompare(nb);
    });

    return sorted;
  }, [files, activeType, query]);

  // counts for tabs
  const counts = useMemo(() => {
    const c = { ALL: 0, PDF: 0, DOCX: 0, TXT: 0, OTHER: 0 } as Record<FileType, number>;
    const filteredByQuery = files.filter((f) => matchesQuery(f, query));
    c.ALL = filteredByQuery.length;
    for (const f of filteredByQuery) {
      const t = getFileType(f.fileName) as Exclude<FileType, 'ALL'>;
      c[t] += 1;
    }
    return c;
  }, [files, query]);

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900">Knowledge Base</h1>
            <p className="text-neutral-500 mt-1">Manage your documents and data sources.</p>
          </div>

          {/* Search */}
          <div className="w-full max-w-sm">
            <div className="relative">
              <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search documents..."
                className="w-full pl-9 pr-3 py-2 rounded-2xl border border-neutral-200 bg-white text-sm text-neutral-800 outline-none focus:border-neutral-400"
              />
            </div>
          </div>
        </div>

        {/* Type Tabs */}
        <div className="flex items-center gap-2 flex-wrap">
          {(['ALL', 'PDF', 'DOCX', 'TXT', 'OTHER'] as FileType[]).map((t) => (
            <button
              key={t}
              onClick={() => setActiveType(t)}
              className={clsx(
                'px-3 py-1.5 rounded-2xl text-sm border transition-colors',
                activeType === t
                  ? 'bg-neutral-900 text-white border-neutral-900'
                  : 'bg-white text-neutral-700 border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300'
              )}
            >
              {t} <span className={clsx('ml-1 text-xs', activeType === t ? 'text-white/80' : 'text-neutral-400')}>({counts[t]})</span>
            </button>
          ))}
        </div>

        {/* Upload Area */}
        <div
          className={clsx(
            'border-2 border-dashed rounded-2xl p-10 text-center transition-colors cursor-pointer bg-white',
            isDragging ? 'border-neutral-500 bg-neutral-50' : 'border-neutral-300 hover:border-neutral-400'
          )}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          onClick={() => document.getElementById('fileInput')?.click()}
        >
          <input
            type="file"
            id="fileInput"
            className="hidden"
            multiple
            onChange={(e) => {
              if (e.target.files) Array.from(e.target.files).forEach(handleFileSelect);
              e.target.value = '';
            }}
          />

          <div className="flex flex-col items-center gap-3">
            <div className="p-4 bg-neutral-900 rounded-full">
              <Upload className="w-8 h-8 text-white" />
            </div>
            <div>
              <p className="text-lg font-medium text-neutral-800">Click to upload or drag and drop</p>
              <p className="text-sm text-neutral-500">PDF, DOCX, TXT supported</p>
            </div>
          </div>
        </div>

        {/* Active Uploads */}
        {uploadTasks.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-neutral-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-neutral-200 bg-neutral-50">
              <h3 className="font-semibold text-neutral-700">Upload Queue ({uploadTasks.length})</h3>
            </div>

            <div className="divide-y divide-neutral-100">
              {uploadTasks.map((task) => (
                <div key={task.id} className="px-6 py-4">
                  <div className="flex justify-between items-center mb-2">
                    <div className="font-medium text-neutral-900">{task.fileName}</div>
                    <div className="text-xs text-neutral-500">{task.status}</div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="flex-1 h-2 bg-neutral-100 rounded-full overflow-hidden">
                      <div
                        className={clsx(
                          'h-full transition-all duration-300',
                          task.status === 'error'
                            ? 'bg-red-500'
                            : task.status === 'completed'
                            ? 'bg-emerald-500'
                            : 'bg-neutral-900'
                        )}
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>

                    <div className="text-sm text-neutral-600 w-12 text-right">{task.progress}%</div>

                    <div className="flex gap-2">
                      {task.status === 'uploading' && (
                        <button
                          onClick={() => handlePause(task)}
                          className="text-neutral-400 hover:text-amber-600"
                          title="Pause"
                        >
                          <PauseCircle className="w-5 h-5" />
                        </button>
                      )}

                      {task.status === 'paused' && (
                        <button
                          onClick={() => handleResume(task)}
                          className="text-neutral-400 hover:text-neutral-900"
                          title="Resume"
                        >
                          <PlayCircle className="w-5 h-5" />
                        </button>
                      )}

                      <button
                        onClick={() => {
                          void handleCancel(task);
                        }}
                        className="text-neutral-400 hover:text-red-600"
                        title="Cancel"
                      >
                        <XCircle className="w-5 h-5" />
                      </button>
                    </div>
                  </div>

                  {task.status === 'error' && task.error && (
                    <div className="mt-2 text-sm text-red-600">{task.error}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* File List */}
        <div className="bg-white rounded-2xl shadow-sm border border-neutral-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-neutral-200 bg-neutral-50">
            <h3 className="font-semibold text-neutral-700">
              Uploaded Files ({visibleFiles.length})
            </h3>
          </div>

          {visibleFiles.length === 0 ? (
            <div className="p-8 text-center text-neutral-400">No matching files.</div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {visibleFiles.map((file) => {
                const type = getFileType(file.fileName);
                return (
                  <div
                    key={file.fileMd5}
                    className="px-6 py-4 flex items-center justify-between hover:bg-neutral-50 transition-colors"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="p-2 bg-neutral-100 rounded-xl">
                        <FileText className="w-6 h-6 text-neutral-700" />
                      </div>

                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => handleOpenFile(file)}
                          className="font-medium text-neutral-900 truncate hover:underline text-left"
                          title="Open file"
                        >
                          {file.fileName}
                        </button>
                        <div className="text-xs text-neutral-500 flex gap-2 flex-wrap">
                          <span className="px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-800">
                            {type}
                          </span>
                          <span>{formatSize(file.totalSize)}</span>
                          <span className="text-neutral-300">•</span>
                          <span className="text-neutral-400">{formatTime(file.createdAt)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <StatusBadge status={file.status} />
                      <button
                        type="button"
                        onClick={() => handleDeleteFile(file)}
                        disabled={deletingMd5 === file.fileMd5}
                        className="p-2 rounded-lg text-neutral-500 hover:text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Delete file"
                      >
                        {deletingMd5 === file.fileMd5 ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const StatusBadge = ({ status }: { status: number }) => {
  const mapStatus = (s: number) => {
    switch (s) {
      case 1:
        return 'completed';
      case 2:
        return 'processing';
      case 0:
        return 'uploading';
      default:
        return 'failed';
    }
  };

  const statusKey = mapStatus(status);

  const styles: Record<string, string> = {
    processing: 'bg-amber-100 text-amber-800',
    completed: 'bg-emerald-100 text-emerald-800',
    failed: 'bg-red-100 text-red-800',
    uploading: 'bg-neutral-200 text-neutral-800',
  };

  const icons: Record<string, React.ReactNode> = {
    processing: <Loader2 className="w-3 h-3 animate-spin" />,
    completed: <CheckCircle className="w-3 h-3" />,
    failed: <AlertCircle className="w-3 h-3" />,
    uploading: <Loader2 className="w-3 h-3 animate-spin" />,
  };

  return (
    <span
      className={clsx(
        'px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5',
        styles[statusKey] || styles.uploading
      )}
    >
      {icons[statusKey] || icons.uploading}
      {statusKey.charAt(0).toUpperCase() + statusKey.slice(1)}
    </span>
  );
};

export default KnowledgeBase;
