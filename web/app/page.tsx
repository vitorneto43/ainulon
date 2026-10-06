"use client";

import { FormEvent, ReactNode, useState } from "react";

type SearchResult = {
  url: string;
  title: string | null;
  description: string | null;
  snippet: string;
  score: number;
};

type SearchResponse = {
  query: string;
  count: number;
  results: SearchResult[];
};

function renderSnippet(snippet: string): ReactNode[] {
  const parts = snippet.split(/(<mark>.*?<\/mark>)/gi);

  return parts.map((part, index) => {
    const match = part.match(/^<mark>(.*?)<\/mark>$/i);

    if (match) {
      return (
        <mark
          key={index}
          className="rounded bg-yellow-100 px-0.5 text-inherit"
        >
          {match[1]}
        </mark>
      );
    }

    return <span key={index}>{part}</span>;
  });
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();

    const term = query.trim();

    if (!term) return;

    setLoading(true);
    setSearched(true);

    try {
      const response = await fetch(
        `https://api.ainulon.com/search?q=${encodeURIComponent(term)}`
      );

      if (!response.ok) {
        throw new Error("Erro ao pesquisar");
      }

      const data: SearchResponse = await response.json();
      setResults(data.results);
    } catch (error) {
      console.error(error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-white text-zinc-900">
      <div
        className={`mx-auto flex max-w-3xl flex-col px-6 ${
          searched ? "pt-12" : "min-h-screen justify-center"
        }`}
      >
        <div className="mb-8 text-center">
          <img
            src="/ainulon-logo.png"
            alt="Ainulon"
            className="mx-auto h-auto w-72"
          />
        </div>

        <form onSubmit={handleSearch} className="w-full">
          <div className="flex overflow-hidden rounded-full border border-zinc-300 bg-white shadow-sm transition focus-within:shadow-md">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Pesquise na web"
              className="flex-1 px-6 py-4 text-lg outline-none"
            />

            <button
              type="submit"
              className="px-7 font-medium text-zinc-700 hover:bg-zinc-50"
            >
              Buscar
            </button>
          </div>
        </form>

        {searched && (
          <section className="mt-10 pb-20">
            {loading ? (
              <p className="text-zinc-500">Pesquisando...</p>
            ) : results.length === 0 ? (
              <p className="text-zinc-500">
                Nenhum resultado encontrado.
              </p>
            ) : (
              <div className="space-y-8">
                {results.map((result) => (
                  <article key={result.url}>
                    <p className="mb-1 truncate text-sm text-zinc-500">
                      {result.url}
                    </p>

                    <a
                      href={result.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xl font-medium text-blue-700 hover:underline"
                    >
                      {result.title || result.url}
                    </a>

                    <p className="mt-2 leading-6 text-zinc-700">
                      {renderSnippet(result.snippet)}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {!searched && (
          <p className="mt-6 text-center text-sm text-zinc-500">
            Busca inteligente. Privacidade por princípio.
          </p>
        )}
      </div>
    </main>
  );
}