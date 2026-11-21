import { useEffect } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Landing() {
  const { user, loading } = useAuth();

  useEffect(() => {
    document.title = 'DocuQite — Grounded Document RAG';
  }, []);

  if (!loading && user) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen bg-[#fafafa] text-neutral-900 flex flex-col justify-between font-sans">
      {/* Navbar */}
      <header className="border-b border-neutral-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="font-semibold text-lg text-neutral-900 tracking-tight">
            DocuQite
          </Link>

          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="px-3 py-1.5 text-sm font-medium text-neutral-700 hover:text-neutral-900 rounded-md transition-colors"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="px-3.5 py-1.5 text-sm font-medium text-white bg-teal-800 hover:bg-teal-900 rounded-md transition-colors"
            >
              Create account
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-16 sm:py-20 space-y-20">
        {/* Hero Section */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-start">
          {/* Left Column */}
          <div className="space-y-6">
            <h1 className="text-4xl sm:text-[44px] font-semibold text-neutral-950 tracking-tight leading-[1.15]">
              Ask your documents. Get answers you can verify.
            </h1>

            <p className="text-base text-neutral-600 leading-relaxed max-w-[60ch]">
              Upload PDFs, Word and PowerPoint files. Every answer points to the document and page it came from, and if the documents don't say, it tells you so.
            </p>

            <div className="flex items-center gap-3 pt-2">
              <Link
                to="/register"
                className="px-4 py-2 bg-teal-800 hover:bg-teal-900 text-white font-medium text-sm rounded-md transition-colors"
              >
                Create account
              </Link>
              <Link
                to="/login"
                className="px-4 py-2 bg-white border border-neutral-300 hover:bg-neutral-50 text-neutral-800 font-medium text-sm rounded-md transition-colors"
              >
                Sign in
              </Link>
            </div>
          </div>

          {/* Right Column: Static Product Preview */}
          <div>
            <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-400 mb-1.5">
              Example
            </div>
            <div className="border border-neutral-200 rounded-md bg-white p-4 space-y-4">
              {/* Question 1 */}
              <div className="flex justify-end">
                <div className="bg-neutral-100 text-neutral-900 text-xs sm:text-sm px-3 py-2 rounded-md max-w-[85%]">
                  How do you protect my data?
                </div>
              </div>

              {/* Answer 1 */}
              <div className="space-y-2.5">
                <p className="text-xs sm:text-sm text-neutral-800 leading-relaxed">
                  Data is encrypted at rest using AES-256 and in transit via TLS 1.3. Access is restricted through role-based access control and audited periodically [1].
                </p>
                <div>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-teal-200 bg-teal-50 text-teal-800">
                    <span className="font-bold">[1]</span>
                    <span>privacy-policy.pdf, p. 5</span>
                  </span>
                </div>
              </div>

              <div className="border-t border-neutral-100 pt-3 space-y-3">
                {/* Question 2 */}
                <div className="flex justify-end">
                  <div className="bg-neutral-100 text-neutral-900 text-xs sm:text-sm px-3 py-2 rounded-md max-w-[85%]">
                    Who won the 2018 World Cup?
                  </div>
                </div>

                {/* Answer 2: Abstained */}
                <div className="border border-neutral-200 bg-neutral-50/70 p-3 rounded-md space-y-1">
                  <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wide">
                    Not found in the uploaded documents
                  </div>
                  <p className="text-xs text-neutral-600 italic">
                    I couldn't find enough information in the uploaded documents to answer this question.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* What it does Section */}
        <section className="border-t border-neutral-200 pt-12 space-y-6">
          <h2 className="text-lg font-semibold text-neutral-900 tracking-tight">
            What it does
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6 text-sm text-neutral-600 leading-relaxed">
            <div>
              <span className="font-semibold text-neutral-900">Hybrid search: </span>
              combines meaning-based and keyword search, then reranks.
            </div>

            <div>
              <span className="font-semibold text-neutral-900">Page-level citations: </span>
              every answer links to its source passage.
            </div>

            <div>
              <span className="font-semibold text-neutral-900">Says "not found": </span>
              declines to answer when the documents don't support one.
            </div>

            <div>
              <span className="font-semibold text-neutral-900">Separate workspaces: </span>
              documents stay isolated per workspace.
            </div>

            <div>
              <span className="font-semibold text-neutral-900">Request tracing: </span>
              per-stage latency and token counts are recorded.
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-neutral-200 bg-white py-6">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-neutral-500">
          <span className="font-medium text-neutral-800">DocuQite</span>
          <a
            href="https://github.com/shahidx05/Enterprise-RAG-platform"
            target="_blank"
            rel="noreferrer"
            className="text-neutral-500 hover:text-neutral-800 transition-colors underline"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
