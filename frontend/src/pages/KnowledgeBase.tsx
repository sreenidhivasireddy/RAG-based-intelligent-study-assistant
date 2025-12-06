import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, XCircle, PauseCircle, PlayCircle } from 'lucide-react';
import { fileApi } from '../api';
import { UploadedFile } from '../types';
import { clsx } from 'clsx';
import SparkMD5 from 'spark-md5';
import { nanoid } from 'nanoid';

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
const MAX_CONCURRENT_UPLOADS = 3;

interface UploadTask {
  id: string; // Request ID / Task ID
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

  const loadFiles = useCallback(async () => {
    try {
      const list = await fileApi.list();
      setFiles(list);
    } catch (error) {
      console.error("Failed to load files", error);
    }
  }, []);

  useEffect(() => {
    loadFiles();
    const interval = setInterval(loadFiles, 5000); // Poll for status updates
    return () => clearInterval(interval);
  }, [loadFiles]);

  // Process Queue Loop
  useEffect(() => {
    const processQueue = async () => {
      if (activeUploadsCount.current >= MAX_CONCURRENT_UPLOADS) return;

      const pendingTask = uploadTasks.find(t => t.status === 'pending');
      if (pendingTask) {
        startUpload(pendingTask.id);
      }
    };

    processQueue();
  }, [uploadTasks]);

  const calculateMD5 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const blobSlice = File.prototype.slice || (File.prototype as any).mozSlice || (File.prototype as any).webkitSlice;
      const chunks = Math.ceil(file.size / CHUNK_SIZE);
      let currentChunk = 0;
      const spark = new SparkMD5.ArrayBuffer();
      const fileReader = new FileReader();

      fileReader.onload = function (e) {
        if (e.target?.result) {
          spark.append(e.target.result as ArrayBuffer);
        }
        currentChunk++;

        if (currentChunk < chunks) {
          loadNext();
        } else {
          resolve(spark.end());
        }
      };

      fileReader.onerror = function () {
        reject('MD5 calculation failed');
      };

      function loadNext() {
        const start = currentChunk * CHUNK_SIZE;
        const end = ((start + CHUNK_SIZE) >= file.size) ? file.size : start + CHUNK_SIZE;
        fileReader.readAsArrayBuffer(blobSlice.call(file, start, end));
      }

      loadNext();
    });
  };

  const updateTask = (id: string, updates: Partial<UploadTask>) => {
    setUploadTasks(prev => prev.map(t => t.id === id ? { ...t, ...updates } : t));
  };

  const startUpload = async (taskId: string) => {
    const task = uploadTasks.find(t => t.id === taskId);
    if (!task) return;

    activeUploadsCount.current++;
    updateTask(taskId, { status: 'hashing' });

    try {
      // 1. Calculate MD5
      const fileMd5 = await calculateMD5(task.file);
      updateTask(taskId, { fileMd5 });

      // 2. Check if file exists (Fast Upload)
      const existingFile = files.find(f => f.fileMd5 === fileMd5);
      if (existingFile) {
        updateTask(taskId, { status: 'completed', progress: 100 });
        activeUploadsCount.current--;
        // Auto-remove from queue after showing completion
        setTimeout(() => {
          setUploadTasks(prev => prev.filter(t => t.id !== taskId));
        }, 1500);
        return; // Done
      }

      // 3. Check resume status
      let uploadedChunks: number[] = [];
      try {
        const status = await fileApi.checkStatus(fileMd5);
        if (status) {
            uploadedChunks = status.uploadedChunks || [];
        }
      } catch (e) {
        // Ignore 404 or other errors, assume fresh upload
      }

      updateTask(taskId, { 
        status: 'uploading', 
        uploadedChunks 
      });

      // 4. Upload Loop
      const abortController = new AbortController();
      updateTask(taskId, { abortController });

      const totalChunks = Math.ceil(task.file.size / CHUNK_SIZE);
      
      for (let i = 0; i < totalChunks; i++) {
        // Check cancellation/pause
        // Note: State inside async loop might be stale if we rely on 'task' variable, so we should query latest or use refs if possible.
        // However, since we are inside the function scope, we can't easily see external state updates without refs or querying.
        // But we can check the abort signal.
        if (abortController.signal.aborted) {
           throw new Error('Cancelled');
        }

        if (uploadedChunks.includes(i)) {
          continue;
        }

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
            totalChunks
          },
          () => {
            // Calculate total progress (simplified)
             // This per-chunk progress is nice but we mostly care about total chunks done.
          },
          abortController.signal
        );

        uploadedChunks.push(i);
        const progress = Math.round((uploadedChunks.length / totalChunks) * 100);
        updateTask(taskId, { uploadedChunks, progress });
      }

      // 5. Merge
      updateTask(taskId, { status: 'merging' });
      await fileApi.merge(fileMd5, task.file.name);
      
      updateTask(taskId, { status: 'completed', progress: 100 });
      loadFiles();
      
      // Auto-remove completed task from queue after 1.5 seconds
      setTimeout(() => {
        setUploadTasks(prev => prev.filter(t => t.id !== taskId));
      }, 1500);

    } catch (error: any) {
      if (error.message === 'Cancelled' || error.name === 'AbortError') {
         updateTask(taskId, { status: 'paused' });
      } else {
         console.error("Upload error:", error);
         updateTask(taskId, { status: 'error', error: error.message || 'Upload failed' });
      }
    } finally {
      activeUploadsCount.current--;
      // Trigger re-evaluation of queue
      setUploadTasks(prev => [...prev]); 
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
      status: 'pending'
    };
    setUploadTasks(prev => [...prev, newTask]);
  };

  const handleCancel = (task: UploadTask) => {
    if (task.abortController) {
      task.abortController.abort();
    }
    setUploadTasks(prev => prev.filter(t => t.id !== task.id));
  };
  
  const handlePause = (task: UploadTask) => {
      if (task.abortController) {
          task.abortController.abort(); // Stop current request
      }
      updateTask(task.id, { status: 'paused', abortController: undefined });
  };

  const handleResume = (task: UploadTask) => {
      updateTask(task.id, { status: 'pending' }); // Reset to pending to be picked up by queue
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
    
    // Less than 1 minute
    if (diff < 60 * 1000) {
      return 'Just now';
    }
    // Less than 1 hour
    if (diff < 60 * 60 * 1000) {
      const minutes = Math.floor(diff / (60 * 1000));
      return `${minutes} min ago`;
    }
    // Less than 24 hours
    if (diff < 24 * 60 * 60 * 1000) {
      const hours = Math.floor(diff / (60 * 60 * 1000));
      return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    }
    // More than 24 hours - show date with year
    const month = date.toLocaleDateString('en-US', { month: 'short' });
    const day = date.getDate();
    const year = date.getFullYear();
    const time = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    return `${month} ${day}, ${time}, ${year}`;
  };

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Knowledge Base</h1>
          <p className="text-gray-500 mt-1">Manage your documents and data sources.</p>
        </div>

        {/* Upload Area */}
        <div
          className={clsx(
            "border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer",
            isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400"
          )}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
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
                if (e.target.files) {
                    Array.from(e.target.files).forEach(handleFileSelect);
                }
                e.target.value = ''; // Reset
            }}
          />
          
          <div className="flex flex-col items-center gap-3">
            <div className="p-4 bg-blue-100 rounded-full">
            <Upload className="w-8 h-8 text-blue-600" />
            </div>
            <div>
            <p className="text-lg font-medium text-gray-700">Click to upload or drag and drop</p>
            <p className="text-sm text-gray-500">PDF, DOCX, TXT supported</p>
            </div>
          </div>
        </div>

        {/* Active Uploads */}
        {uploadTasks.length > 0 && (
             <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-8">
                <div className="px-6 py-4 border-b border-gray-100 bg-gray-50/50">
                    <h3 className="font-semibold text-gray-700">Upload Queue ({uploadTasks.length})</h3>
                </div>
                <div className="divide-y divide-gray-100">
                    {uploadTasks.map(task => (
                        <div key={task.id} className="px-6 py-4">
                            <div className="flex justify-between items-center mb-2">
                                <div className="font-medium text-gray-900">{task.fileName}</div>
                                <div className="text-xs text-gray-500">{task.status}</div>
                            </div>
                            <div className="flex items-center gap-4">
                                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                                    <div 
                                        className={clsx(
                                            "h-full transition-all duration-300",
                                            task.status === 'error' ? "bg-red-500" : 
                                            task.status === 'completed' ? "bg-green-500" : "bg-blue-600"
                                        )}
                                        style={{ width: `${task.progress}%` }} 
                                    />
                                </div>
                                <div className="text-sm text-gray-600 w-12 text-right">{task.progress}%</div>
                                <div className="flex gap-2">
                                    {task.status === 'uploading' && (
                                        <button onClick={() => handlePause(task)} className="text-gray-400 hover:text-yellow-600">
                                            <PauseCircle className="w-5 h-5" />
                                        </button>
                                    )}
                                    {task.status === 'paused' && (
                                        <button onClick={() => handleResume(task)} className="text-gray-400 hover:text-blue-600">
                                            <PlayCircle className="w-5 h-5" />
                                        </button>
                                    )}
                                    <button onClick={() => handleCancel(task)} className="text-gray-400 hover:text-red-600">
                                        <XCircle className="w-5 h-5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        )}

        {/* File List */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 bg-gray-50/50">
            <h3 className="font-semibold text-gray-700">Uploaded Files ({files.length})</h3>
          </div>
          
          {files.length === 0 ? (
            <div className="p-8 text-center text-gray-400">No files uploaded yet.</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {files.map((file) => (
                <div key={file.fileMd5} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-4">
                    <div className="p-2 bg-gray-100 rounded-lg">
                      <FileText className="w-6 h-6 text-gray-600" />
                    </div>
                    <div>
                      <div className="font-medium text-gray-900">{file.fileName}</div>
                      <div className="text-xs text-gray-500 flex gap-2">
                      <span>{formatSize(file.totalSize)}</span>
                      <span>•</span>
                      <span className="text-gray-400">{formatTime(file.createdAt)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <StatusBadge status={file.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const StatusBadge = ({ status }: { status: number }) => {
  const mapStatus = (s: number) => {
      switch(s) {
          case 1: return 'completed';
          case 2: return 'processing';
          case 0: return 'uploading';
          default: return 'failed';
      }
  };
  
  const statusKey = mapStatus(status);

  const styles = {
    uploaded: "bg-blue-100 text-blue-700",
    processing: "bg-yellow-100 text-yellow-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    uploading: "bg-blue-100 text-blue-700"
  };

  const icons = {
    uploaded: <Loader2 className="w-3 h-3 animate-spin" />,
    processing: <Loader2 className="w-3 h-3 animate-spin" />,
    completed: <CheckCircle className="w-3 h-3" />,
    failed: <AlertCircle className="w-3 h-3" />,
    uploading: <Loader2 className="w-3 h-3 animate-spin" />
  };

  const key = statusKey as keyof typeof styles;

  return (
    <span className={clsx("px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5", styles[key] || styles.uploaded)}>
      {icons[key]}
      {statusKey.charAt(0).toUpperCase() + statusKey.slice(1)}
    </span>
  );
};

export default KnowledgeBase;
