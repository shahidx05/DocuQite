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

  useEffect(() => {
    fetchMetricsAndTraces();
  }, [fetchMetricsAndTraces]);

  const hasMockProvider =
    traces.some((t) => t.provider === 'mock') || (traces.length === 0 && true);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-sm">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-sm text-slate-500 font-medium">Loading execution metrics & traces...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
        <button
          type="button"
          onClick={fetchMetricsAndTraces}
          className="text-xs font-semibold text-red-700 hover:text-red-900 underline cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  const isZeroTraces = !metrics || metrics.request_count === 0;

  return (
    <div className="space-y-6">
      {/* Provider Notice */}
      {hasMockProvider && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2.5 shadow-sm">
          <svg className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <span className="font-semibold">Mock LLM Provider Notice:</span> The backend is currently operating with{' '}
            <code className="bg-amber-100/70 px-1 py-0.5 rounded font-mono text-[11px]">LLM_PROVIDER=mock</code>. Latency,
            token metrics, and tokens per second for mock requests are simulated and do not reflect real Gemini API network
            overhead or production pricing.
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Request Count */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Requests</div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {metrics?.request_count ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Recorded executions</div>
        </div>

        {/* Abstain Rate */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Abstain Rate</div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.abstain_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Grounded refusal rate</div>
        </div>

        {/* Error Rate */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Error Rate</div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Failed user requests</div>
        </div>

        {/* Total Cost */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Estimated Cost</div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            ${metrics?.total_estimated_cost_usd ? metrics.total_estimated_cost_usd.toFixed(4) : '0.0000'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">USD token expenditure</div>
        </div>
      </div>

      {isZeroTraces ? (
        /* Zero Traces Empty State */
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-sm">
          <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-800">No execution traces recorded</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
            Ask a question in the Chat tab to start generating real-time per-stage latency percentiles and token traces.
          </p>
        </div>
      ) : (
        <>
          {/* Per-Stage Latency Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
              <h2 className="text-sm font-semibold text-slate-900">Per-Stage Latency (p50 / p95)</h2>
              <span className="text-xs text-slate-400">All measurements in milliseconds</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-xs font-semibold">
                  <tr>
                    <th scope="col" className="px-5 py-3">Stage</th>
                    <th scope="col" className="px-4 py-3">Description</th>
                    <th scope="col" className="px-4 py-3 text-right">p50 Latency</th>
                    <th scope="col" className="px-4 py-3 text-right">p95 Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  <tr>
                    <td className="px-5 py-3 font-semibold text-slate-900">Total Execution</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">End-to-end request duration</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.total_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-indigo-600 font-semibold">{metrics.total_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 font-medium text-slate-800">Follow-up Rewrite</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">Standalone query reformulation</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.rewrite_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.rewrite_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 font-medium text-slate-800">Bi-Encoder Embed</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">Dense (bge-small) + Sparse (BM25) vector generation</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.embed_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.embed_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 font-medium text-slate-800">Qdrant Search</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">Hybrid vector querying with RRF fusion</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.qdrant_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.qdrant_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 font-medium text-slate-800">Cross-Encoder Rerank</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">ms-marco-MiniLM candidate scoring & thresholding</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.rerank_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.rerank_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                  <tr>
                    <td className="px-5 py-3 font-medium text-slate-800">LLM Generation</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">Grounded response generation</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.llm_ms?.p50.toFixed(1)} ms</td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{metrics.llm_ms?.p95.toFixed(1)} ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Latest 20 Traces Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
              <h2 className="text-sm font-semibold text-slate-900">Latest Execution Traces</h2>
              <span className="text-xs text-slate-400">Showing last {traces.length} requests</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-xs font-semibold">
                  <tr>
                    <th scope="col" className="px-4 py-3">Timestamp</th>
                    <th scope="col" className="px-3 py-3">Source</th>
                    <th scope="col" className="px-3 py-3">Provider</th>
                    <th scope="col" className="px-3 py-3 text-right">Total Latency</th>
                    <th scope="col" className="px-3 py-3 text-center">Abstained</th>
                    <th scope="col" className="px-3 py-3 text-right">Tokens</th>
                    <th scope="col" className="px-3 py-3 text-right">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {traces.map((trace) => (
                    <tr key={trace.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-600 font-mono">
                        {new Date(trace.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className="uppercase text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                          {trace.source}
                        </span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${
                          trace.provider === 'mock'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                        }`}>
                          {trace.provider}
                        </span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-right text-xs font-mono">
                        {trace.total_ms} ms
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-center">
                        {trace.abstained ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                            Abstained
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Answered
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-right text-xs text-slate-600 font-mono">
                        {trace.input_tokens} / {trace.output_tokens}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-right text-xs text-slate-600 font-mono">
                        ${trace.estimated_cost_usd ? trace.estimated_cost_usd.toFixed(4) : '0.0000'}
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
