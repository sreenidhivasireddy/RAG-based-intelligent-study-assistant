import React from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { EvaluationRegressionPoint } from '../types';

type Props = {
  source: 'fixed' | 'synthetic';
  points: EvaluationRegressionPoint[];
};

const EmptyState = ({ source }: { source: 'fixed' | 'synthetic' }) => (
  <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50 p-6 text-sm text-neutral-500">
    No regression history available for the {source} dataset.
  </div>
);

const FixedRegressionChart = ({ points }: { points: EvaluationRegressionPoint[] }) => {
  if (!points.length) return <EmptyState source="fixed" />;
  const data = points;

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
          <XAxis dataKey="run_label" stroke="#737373" fontSize={12} />
          <YAxis domain={[0, 5]} stroke="#737373" fontSize={12} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="avg_groundedness" stroke="#111827" strokeWidth={2} dot={{ r: 2 }} name="Groundedness" />
          <Line type="monotone" dataKey="avg_relevance" stroke="#0f766e" strokeWidth={2} dot={{ r: 2 }} name="Relevance" />
          <Line type="monotone" dataKey="avg_overall" stroke="#b45309" strokeWidth={2} dot={{ r: 2 }} name="Overall" />
          <Line type="monotone" dataKey="avg_similarity" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} name="Similarity" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

const SyntheticRegressionChart = ({ points }: { points: EvaluationRegressionPoint[] }) => {
  if (!points.length) return <EmptyState source="synthetic" />;
  const data = points;

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
          <XAxis dataKey="run_label" stroke="#737373" fontSize={12} />
          <YAxis domain={[0, 5]} stroke="#737373" fontSize={12} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="avg_groundedness" stroke="#111827" strokeWidth={2} dot={{ r: 2 }} name="Groundedness" />
          <Line type="monotone" dataKey="avg_relevance" stroke="#0f766e" strokeWidth={2} dot={{ r: 2 }} name="Relevance" />
          <Line type="monotone" dataKey="avg_overall" stroke="#b45309" strokeWidth={2} dot={{ r: 2 }} name="Overall" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

const EvaluationRegressionChart: React.FC<Props> = ({ source, points }) => {
  if (source === 'fixed') {
    return <FixedRegressionChart points={points} />;
  }
  return <SyntheticRegressionChart points={points} />;
};

export default EvaluationRegressionChart;
