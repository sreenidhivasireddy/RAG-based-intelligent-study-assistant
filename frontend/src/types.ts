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
  sources?: SearchResult[]; // RAG feature: detailed search results cited by the answer
  source_files?: string[]; // RAG feature: source file names cited by the answer
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

export type QuizDifficulty = 'easy' | 'medium' | 'hard';
export type QuizBloomLevel = 'understand' | 'apply' | 'analyze';
export type QuizQuestionType = 'MCQ';

export interface QuizQuestion {
  type: QuizQuestionType;
  question: string;
  options?: string[];
  correct_answer?: string;
  explanation: string;
}

export interface QuizResponse {
  quiz_title: string;
  difficulty: QuizDifficulty;
  questions: QuizQuestion[];
}

export type EvalProvider = 'auto' | 'heuristic' | 'ragas' | 'azure_ai_evaluation';
export type DatasetSource = 'fixed' | 'synthetic' | 'both';
export type QuestionDifficulty = 'easy' | 'medium' | 'hard';

export interface EvalMetric {
  score: number;
  reasoning: string;
}

export interface RagEvaluationResponse {
  provider_requested: EvalProvider;
  provider_used: 'heuristic' | 'ragas' | 'azure_ai_evaluation';
  fallback_used: boolean;
  metrics: {
    groundedness: EvalMetric;
    relevance: EvalMetric;
    faithfulness: EvalMetric;
  };
  overall_score: number;
  evaluated_at: string;
}

export interface RagBatchDatasetItem {
  id?: string;
  question: string;
  reference_answer?: string;
}

export interface RagBatchResultItem {
  id?: string;
  question: string;
  reference_answer?: string;
  generated_answer: string;
  retrieved_chunks: string[];
  groundedness: number;
  relevance: number;
  faithfulness: number;
  overall_score: number;
  status: 'ok' | 'error';
  error?: string;
}

export interface RagBatchEvaluationResponse {
  provider_used: 'azure_ai_evaluation';
  total_questions: number;
  succeeded: number;
  failed: number;
  average_scores: {
    groundedness: number;
    relevance: number;
    faithfulness: number;
    overall_score: number;
  };
  results: RagBatchResultItem[];
  evaluated_at: string;
}

export interface EvaluationSummary {
  source: DatasetSource | 'overall';
  total: number;
  ok: number;
  failed: number;
  avg_groundedness: number;
  avg_relevance: number;
  avg_overall: number;
  avg_similarity?: number | null;
}

export interface EvaluationRegressionPoint {
  run_id: string;
  run_label: string;
  timestamp: string;
  dataset_source: DatasetSource;
  avg_groundedness: number;
  avg_relevance: number;
  avg_overall: number;
  avg_similarity?: number | null;
}

export interface EvaluationRegressionHistory {
  fixed: EvaluationRegressionPoint[];
  synthetic: EvaluationRegressionPoint[];
}

export interface AutomatedEvalResultItem {
  id?: string;
  question: string;
  expected_answer?: string;
  generated_answer: string;
  retrieved_chunks: string[];
  groundedness: number;
  relevance: number;
  similarity?: number | null;
  overall_score: number;
  status: 'ok' | 'error';
  error?: string;
  source: 'fixed' | 'synthetic';
  topic?: string | null;
  difficulty?: QuestionDifficulty | null;
}

export interface AutomatedEvalResponse {
  run_id: string;
  mode: DatasetSource;
  dataset_source: DatasetSource;
  provider_used: 'azure_ai_evaluation';
  summary: EvaluationSummary;
  summaries: EvaluationSummary[];
  results: AutomatedEvalResultItem[];
  regression_history: EvaluationRegressionHistory;
  evaluated_at: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  pipeline_version?: string;
}
