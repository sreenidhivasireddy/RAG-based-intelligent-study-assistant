import React, { useEffect, useMemo, useState } from 'react';
import { BarChart3, Loader2, Play } from 'lucide-react';
import { evaluationApi } from '../api';
import {
  AutomatedEvalResponse,
  AutomatedEvalResultItem,
  DatasetSource,
  EvaluationRegressionHistory,
  EvaluationRegressionPoint,
  EvaluationSummary,
} from '../types';
import EvaluationRegressionChart from '../components/EvaluationRegressionChart';

const score5 = (v?: number | null) => `${(v || 0).toFixed(2)} / 5`;
const HISTORY_STORAGE_KEY = 'evaluation_regression_history';

const sourceLabel = (source: string) => source.charAt(0).toUpperCase() + source.slice(1);

const difficultyClasses: Record<string, string> = {
  easy: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  hard: 'bg-rose-50 text-rose-700 border-rose-200',
};

const datasetSourcesForMode = (mode: DatasetSource): Array<'fixed' | 'synthetic'> => {
  if (mode === 'both') return ['fixed', 'synthetic'];
  return [mode];
};

const emptyHistory: EvaluationRegressionHistory = {
  fixed: [],
  synthetic: [],
};

const readStoredHistory = (): EvaluationRegressionHistory => {
  if (typeof window === 'undefined') return emptyHistory;
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return emptyHistory;
    const parsed = JSON.parse(raw) as Partial<EvaluationRegressionHistory>;
    return {
      fixed: Array.isArray(parsed.fixed) ? parsed.fixed : [],
      synthetic: Array.isArray(parsed.synthetic) ? parsed.synthetic : [],
    };
  } catch {
    return emptyHistory;
  }
};

const writeStoredHistory = (history: EvaluationRegressionHistory) => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
};

const Evaluation: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<AutomatedEvalResponse | null>(null);
  const [datasetSource, setDatasetSource] = useState<DatasetSource>('synthetic');
  const [historyBySource, setHistoryBySource] = useState<EvaluationRegressionHistory>(() => {
    const stored = readStoredHistory();
    if (stored.synthetic.length > 20) {
      const migrated = { ...stored, synthetic: [] };
      writeStoredHistory(migrated);
      return migrated;
    }
    return stored;
  });

  useEffect(() => {
    writeStoredHistory(historyBySource);
  }, [historyBySource]);

  useEffect(() => {
    let cancelled = false;
    const sources = datasetSourcesForMode(datasetSource);

    Promise.all(
      sources.map(async (source) => {
        try {
          const points = await evaluationApi.getHistory(source);
          return [source, points] as const;
        } catch {
          return [source, [] as EvaluationRegressionPoint[]] as const;
        }
      })
    ).then((entries) => {
      if (cancelled) return;
      setHistoryBySource((prev) => {
        const next: EvaluationRegressionHistory = { ...emptyHistory, ...prev };
        for (const [source, points] of entries) {
          next[source] = points;
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [datasetSource]);

  const run = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await evaluationApi.runEvaluationPipeline({
        mode: datasetSource,
        dataset_source: datasetSource,
      });
      setResult(res);
      setHistoryBySource(res.regression_history);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Evaluation run failed.');
    } finally {
      setLoading(false);
    }
  };

  const summaries = useMemo(() => {
    if (!result) return [];
    if (result.mode !== 'both') return [];
    const fixedCount = result.results.filter((row) => row.source === 'fixed').length;
    const syntheticCount = result.results.filter((row) => row.source === 'synthetic').length;
    return result.summaries.map((summary) => {
      if (summary.source === 'fixed') {
        return { ...summary, total: fixedCount };
      }
      if (summary.source === 'synthetic') {
        return { ...summary, total: syntheticCount };
      }
      if (summary.source === 'overall') {
        return { ...summary, total: fixedCount + syntheticCount };
      }
      return summary;
    });
  }, [result]);

  const datasetSections = useMemo(() => {
    if (!result) return [];
    if (result.mode !== 'both') {
      return [
        {
          source: result.dataset_source as 'fixed' | 'synthetic',
          title: sourceLabel(result.dataset_source),
          rows: result.results,
          summary: result.summary,
        },
      ];
    }
    return [
      {
        source: 'fixed' as const,
        title: 'Fixed',
        rows: result.results.filter((row) => row.source === 'fixed'),
        summary: result.summaries.find((summary) => summary.source === 'fixed') ?? result.summary,
      },
      {
        source: 'synthetic' as const,
        title: 'Synthetic',
        rows: result.results.filter((row) => row.source === 'synthetic'),
        summary: result.summaries.find((summary) => summary.source === 'synthetic') ?? result.summary,
      },
    ].filter((group) => group.rows.length > 0);
  }, [result]);

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">Automated RAG Evaluation</h1>
          <p className="text-neutral-500 mt-1">
            Runs fixed and synthetic evaluation sets through the RAG pipeline and scores them with Azure AI evaluation.
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-neutral-200 p-6 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="text-sm text-neutral-700 flex items-center gap-3">
              <span className="font-medium">Dataset Source</span>
              <select
                value={datasetSource}
                onChange={(e) => setDatasetSource(e.target.value as DatasetSource)}
                className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-900"
              >
                <option value="synthetic">Synthetic</option>
                <option value="fixed">Fixed</option>
                <option value="both">Both</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-neutral-900 text-white text-sm hover:bg-neutral-800 disabled:opacity-60"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {loading ? 'Running Evaluation...' : 'Run Evaluation'}
          </button>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
              {error}
            </div>
          )}

        </div>

        {result && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {summaries.map((summary) => (
                <SummaryCard key={summary.source} summary={summary} />
              ))}
            </div>

            {datasetSections.map((group) => (
              <div key={group.title} className="bg-white rounded-2xl border border-neutral-200 p-6 space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-neutral-900">
                    {result.mode === 'both' ? 'Both (Fixed and Synthetic) Results' : `${group.title} Results`}
                  </h2>
                  <span className="text-xs text-neutral-500">{group.rows.length} questions</span>
                </div>
                {result.mode !== 'both' && <SummaryCard summary={group.summary} />}
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-base font-semibold text-neutral-900">Regression Tracking</h3>
                      <button
                        type="button"
                        onClick={() =>
                          setHistoryBySource((prev) => {
                            const next = { ...prev, [group.source]: [] };
                            writeStoredHistory(next);
                            return next;
                          })
                        }
                        className="rounded-lg border border-neutral-300 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50"
                      >
                        Clear History
                      </button>
                    </div>
                    <p className="text-sm text-neutral-500">
                      {group.title} score trend across recent evaluation runs.
                    </p>
                  </div>
                  <DatasetRegressionPanel
                    key={`regression-${group.source}`}
                    source={group.source}
                    points={historyBySource[group.source]}
                  />
                </div>
                <ResultsTable rows={group.rows} />
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
};

const SummaryCard = ({ summary }: { summary: EvaluationSummary }) => (
  <div className="rounded-2xl border border-neutral-200 bg-white p-5 space-y-3">
    <div className="flex items-center justify-between">
      <h2 className="text-lg font-semibold text-neutral-900">{sourceLabel(summary.source)}</h2>
      <span className="rounded-full border border-neutral-300 bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700">
        total {summary.total}
      </span>
    </div>
    <div className="grid grid-cols-2 gap-3 text-sm">
      <MetricCard title="Groundedness" score={summary.avg_groundedness} />
      <MetricCard title="Relevance" score={summary.avg_relevance} />
      <MetricCard title="Overall" score={summary.avg_overall} />
      <MetricCard title="Similarity" score={summary.avg_similarity} hideWhenEmpty />
    </div>
    <div className="text-xs text-neutral-500">
      ok: {summary.ok} | failed: {summary.failed}
    </div>
  </div>
);

const MetricCard = ({
  title,
  score,
  hideWhenEmpty = false,
}: {
  title: string;
  score?: number | null;
  hideWhenEmpty?: boolean;
}) => {
  const isMissing = score == null || Number.isNaN(Number(score));
  if (hideWhenEmpty && isMissing) return null;

  return (
    <div className="rounded-xl border border-neutral-200 p-3 bg-neutral-50">
      <div className="text-xs text-neutral-500">{title}</div>
      <div className="text-lg font-semibold text-neutral-900 inline-flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-neutral-500" />
        {isMissing ? 'n/a' : score5(score)}
      </div>
    </div>
  );
};

const DatasetRegressionPanel = ({
  source,
  points,
}: {
  source: 'fixed' | 'synthetic';
  points: EvaluationRegressionPoint[];
}) => {
  if (points.length < 2) return null;

  return (
    <div key={`panel-${source}`} className="rounded-2xl border border-neutral-200 bg-neutral-50 p-4">
      <div className="mb-3 text-sm font-medium text-neutral-700">
        {sourceLabel(source)} Regression Graph
      </div>
      <EvaluationRegressionChart key={`chart-${source}`} source={source} points={points} />
    </div>
  );
};

const ResultsTable = ({ rows }: { rows: AutomatedEvalResultItem[] }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-neutral-500 border-b border-neutral-200">
          <th className="py-2 pr-3">#</th>
          <th className="py-2 pr-3">Question</th>
          <th className="py-2 pr-3">Groundedness</th>
          <th className="py-2 pr-3">Relevance</th>
          <th className="py-2 pr-3">Similarity</th>
          <th className="py-2 pr-3">Overall</th>
          <th className="py-2 pr-3">Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, idx) => (
          <tr key={`${row.id || idx}`} className="border-b border-neutral-100 align-top">
            <td className="py-2 pr-3 text-neutral-500">{idx + 1}</td>
            <td className="py-2 pr-3 min-w-[420px]">
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-medium text-neutral-900">{row.question}</div>
                {row.source === 'fixed' && row.difficulty && (
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${difficultyClasses[row.difficulty]}`}>
                    {row.difficulty}
                  </span>
                )}
              </div>
              <div className="text-xs text-neutral-500 mt-1">
                source: {row.source}
                {row.topic ? ` | topic: ${row.topic}` : ''}
                {' | '}
                chunks: {row.retrieved_chunks.length}
              </div>
            </td>
            <td className="py-2 pr-3">{score5(row.groundedness)}</td>
            <td className="py-2 pr-3">{score5(row.relevance)}</td>
            <td className="py-2 pr-3">{row.similarity == null ? '—' : score5(row.similarity)}</td>
            <td className="py-2 pr-3">{score5(row.overall_score)}</td>
            <td className="py-2 pr-3">
              {row.status === 'ok' ? (
                <span className="text-emerald-700">ok</span>
              ) : (
                <span className="text-red-700" title={row.error || ''}>error</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default Evaluation;
