import { useState, useEffect } from 'react';
import { settingsApi } from '../../api/client';

/**
 * SettingsPanel — lets the user toggle between local (Ollama) and cloud LLMs.
 * Uses /settings/ollama which returns { use_local_llm: bool, provider_order: string[] }
 */

// Backend provider_order values → display labels
const PROVIDER_LABELS = {
  gemini: 'Gemini (cloud)',
  groq: 'Groq (cloud)',
  ollama: 'Ollama (local)',
};

export default function SettingsPanel() {
  const [useLocal, setUseLocal] = useState(false);
  const [providerOrder, setProviderOrder] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    settingsApi
      .getOllama()
      .then((data) => {
        setUseLocal(data?.use_local_llm ?? false);
        // Backend returns provider_order: ["gemini","groq","ollama"]
        setProviderOrder(data?.provider_order ?? []);
      })
      .catch((err) => setError(err.message ?? 'Failed to load settings'))
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async () => {
    const next = !useLocal;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const result = await settingsApi.setOllama(next);
      setUseLocal(result?.use_local_llm ?? next);
      // Update provider_order from backend response
      setProviderOrder(result?.provider_order ?? []);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err.message ?? 'Failed to save setting');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* LLM Mode */}
      <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4">
        <h3 className="font-mono text-sm font-semibold text-tl-t1 uppercase tracking-wider mb-3">
          LLM Provider
        </h3>

        {loading ? (
          <div className="h-8 w-40 bg-tl-b2 animate-pulse rounded" />
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              {/* Toggle switch */}
              <button
                onClick={handleToggle}
                disabled={saving}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  useLocal ? 'bg-tl-gold' : 'bg-tl-b2'
                } disabled:opacity-50`}
                aria-label="Toggle local LLM"
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-tl-bg transition-transform ${
                    useLocal ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>

              <div>
                <p className="text-sm text-tl-t1 font-mono">
                  {useLocal ? 'Local-first (Ollama)' : 'Cloud-first (Gemini)'}
                </p>
                <p className="text-xs text-tl-t3 font-mono">
                  {useLocal
                    ? 'Data stays on device — Ollama must be running'
                    : 'Best quality — requires API keys'}
                </p>
              </div>
            </div>

            {/* Provider order */}
            <div>
              <p className="text-xs font-mono text-tl-t3 mb-1.5 uppercase tracking-wider">
                Fallback order
              </p>
              <ol className="space-y-1">
                {providerOrder.map((providerKey, i) => {
                  // Backend returns lowercase keys: "gemini", "groq", "ollama"
                  const label = PROVIDER_LABELS[providerKey] ?? providerKey;
                  return (
                  <li key={providerKey} className="flex items-center gap-2 text-xs font-mono">
                    <span
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                        i === 0
                          ? 'bg-tl-gold text-tl-bg'
                          : 'bg-tl-b2 text-tl-t3'
                      }`}
                    >
                      {i + 1}
                    </span>
                    <span className={i === 0 ? 'text-tl-t1' : 'text-tl-t3'}>{label}</span>
                  </li>
                  );
                })}
              </ol>
            </div>

            {saved && (
              <p className="text-xs font-mono text-tl-hi mt-3">Settings saved!</p>
            )}
            {error && (
              <p className="text-xs font-mono text-tl-low mt-3">{error}</p>
            )}
          </>
        )}
      </section>

      {/* About */}
      <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4">
        <h3 className="font-mono text-sm font-semibold text-tl-t1 uppercase tracking-wider mb-2">
          About TraceLit
        </h3>
        <p className="text-xs text-tl-t3 font-mono leading-relaxed">
          Sentence-level attribution engine for academic literature.
          Built with HAVF (Hallucination-Aware Verification Framework) —
          every response sentence is verified against your uploaded papers.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {['HAVF', 'RAG', 'Local-first', 'Privacy-preserving'].map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-tl-b2 text-tl-t3"
            >
              {tag}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
