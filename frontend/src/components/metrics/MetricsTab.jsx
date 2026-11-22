import { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';

export default function MetricsTab({ workspaceId }) {
  const [metrics, setMetrics] = useState(null);
  const [traces, setTraces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchMetricsAndTraces = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [metricsRes, tracesRes] = await Promise.all([
        api.get(`/api/workspaces/${workspaceId}/metrics`),
        api.get(`/api/workspaces/${workspaceId}/traces?limit=20`),
      ]);
      setMetrics(metricsRes.data);
      setTraces(tracesRes.data);
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'string' ? err.response.data : null) ||
        'Failed to load metrics and traces.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  // Refetch when tab is mounted / opened
  useEffect(() => {
    fetchMetricsAndTraces();
  }, [fetchMetricsAndTraces]);

  const hasMockProvider =
    traces.some((t) => t.provider === 'mock') ||
    (metrics && metrics.request_count > 0 && traces.length > 0 && traces[0].provider === 'mock');

  if (loading) {
    return (
      <div className="bg-white rounded-md border border-neutral-200 p-10 text-center">
        <div className="w-6 h-6 border-2 border-teal-800 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
        <p className="text-xs text-neutral-500 font-medium">Loading metrics and traces...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3.5 rounded-md bg-red-50 border border-red-200 text-xs text-red-700 flex items-center justify-between">
        <span>{error}</span>
        <button
          type="button"
          onClick={fetchMetricsAndTraces}
          className="font-medium text-red-800 hover:text-red-900 underline ml-3 cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  const isZeroTraces = !metrics || metrics.request_count === 0;

  return (
    <div className="space-y-6">
      {/* Top Controls: Title and Refresh Button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-neutral-900">Workspace Metrics</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Per-stage execution latency percentiles, token usage, and trace logs.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchMetricsAndTraces}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-neutral-700 bg-white hover:bg-neutral-50 border border-neutral-300 rounded-md transition-colors cursor-pointer"
        >
          <svg className="w-3.5 h-3.5 text-neutral-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Mock Provider Notice */}
      {hasMockProvider && (
        <div className="p-3 bg-neutral-100 border border-neutral-200 text-xs text-neutral-700 rounded-md">
          <span className="font-semibold text-neutral-900">Mock LLM: </span>
          LLM latency and tokens/sec are not meaningful.
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-md border border-neutral-200">
          <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">Request Count</div>
          <div className="text-2xl font-semibold text-neutral-900 mt-1.5">
            {metrics?.request_count ?? 0}
          </div>
          <div className="text-[11px] text-neutral-400 mt-0.5">Recorded requests</div>
        </div>

        <div className="bg-white p-4 rounded-md border border-neutral-200">
          <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">Abstain Rate</div>
          <div className="text-2xl font-semibold text-neutral-900 mt-1.5">
            {metrics ? `${(metrics.abstain_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="text-[11px] text-neutral-400 mt-0.5">Unanswerable queries refused</div>
        </div>

        <div className="bg-white p-4 rounded-md border border-neutral-200">
          <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">Error Rate</div>
          <div className="text-2xl font-semibold text-neutral-900 mt-1.5">
            {metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="text-[11px] text-neutral-400 mt-0.5">Failed pipeline requests</div>
        </div>

        <div className="bg-white p-4 rounded-md border border-neutral-200">
          <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">Total Estimated Cost</div>
          <div className="text-2xl font-semibold text-neutral-900 mt-1.5">
            ${metrics?.total_estimated_cost_usd ? metrics.total_estimated_cost_usd.toFixed(4) : '0.0000'}
          </div>
          <div className="text-[11px] text-neutral-400 mt-0.5">USD token expenditure</div>
        </div>
      </div>

      {isZeroTraces ? (
        <div className="bg-white rounded-md border border-neutral-200 p-10 text-center">
          <h3 className="text-sm font-medium text-neutral-800">No traces recorded</h3>
          <p className="text-xs text-neutral-500 mt-1 max-w-sm mx-auto">
            Questions asked in the Chat tab will record execution latencies and token usage here.
          </p>
        </div>
      ) : (
        <>
          {/* Table of p50 and p95 per stage: total, embed, qdrant, rerank, llm */}
          <div className="bg-white rounded-md border border-neutral-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50/50">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-700">
                Latency by Stage (p50 / p95)
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-neutral-200 text-left text-xs">
                <thead className="bg-neutral-50 text-neutral-500 font-medium">
                  <tr>
                    <th scope="col" className="px-4 py-2.5">Stage</th>
                    <th scope="col" className="px-4 py-2.5 text-right">p50 Latency</th>
                    <th scope="col" className="px-4 py-2.5 text-right">p95 Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 bg-white text-neutral-800">
                  <tr>
                    <td className="px-4 py-2.5 font-medium text-neutral-900">Total Request</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.total_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 text-right font-mono font-medium text-teal-800">{metrics.total_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">Embed (Dense + Sparse)</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.embed_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.embed_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">Qdrant Search</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.qdrant_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.qdrant_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">Rerank (Cross-Encoder)</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.rerank_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.rerank_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">LLM Generation</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.llm_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-2.5 text-right font-mono">{metrics.llm_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Table of Latest 20 Traces: time, source (ask/chat), provider, total ms, abstained, input/output tokens */}
          <div className="bg-white rounded-md border border-neutral-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50/50 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-700">
                Latest Traces ({traces.length})
              </h3>
              <span className="text-[11px] text-neutral-400">Newest first</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-neutral-200 text-left text-xs">
                <thead className="bg-neutral-50 text-neutral-500 font-medium">
                  <tr>
                    <th scope="col" className="px-4 py-2.5">Time</th>
                    <th scope="col" className="px-3 py-2.5">Source</th>
                    <th scope="col" className="px-3 py-2.5">Provider</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Total Latency</th>
                    <th scope="col" className="px-3 py-2.5 text-center">Abstained</th>
                    <th scope="col" className="px-4 py-2.5 text-right">Tokens (In / Out)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 bg-white text-neutral-800">
                  {traces.map((trace) => (
                    <tr key={trace.id} className="hover:bg-neutral-50/70">
                      <td className="px-4 py-2.5 whitespace-nowrap font-mono text-[11px] text-neutral-600">
                        {new Date(trace.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className="uppercase text-[10px] font-semibold px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-700 border border-neutral-200">
                          {trace.source}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                          trace.provider === 'mock'
                            ? 'bg-neutral-100 text-neutral-700 border-neutral-200'
                            : 'bg-teal-50 text-teal-800 border-teal-200'
                        }`}>
                          {trace.provider}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap text-right font-mono">
                        {trace.total_ms} ms
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap text-center">
                        {trace.abstained ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-neutral-100 text-neutral-700 border border-neutral-200">
                            Yes
                          </span>
                        ) : (
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-teal-50 text-teal-800 border-teal-200">
                            No
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 whitespace-nowrap text-right font-mono text-[11px]">
                        {trace.input_tokens} / {trace.output_tokens}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
