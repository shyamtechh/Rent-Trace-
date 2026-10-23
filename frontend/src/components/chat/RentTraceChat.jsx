import { useEffect, useRef, useState } from 'react';
import {
  CHAT_QUICK_ACTIONS,
  CHAT_WELCOME_MESSAGE,
  fetchChatStatus,
  sendChatMessage,
} from '../../services/chat';

const INITIAL_MESSAGES = [{ role: 'assistant', content: CHAT_WELCOME_MESSAGE }];

function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-md bg-emerald-700 text-white'
            : 'rounded-bl-md border border-slate-200 bg-white text-slate-800'
        }`}
      >
        {message.content}
        {!isUser && message.answerKind && (
          <p className="mt-2 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
            {message.answerKind === 'renttrace_data'
              ? 'Answer from RentTrace data'
              : message.answerKind === 'data_unavailable'
                ? 'RentTrace data unavailable'
                : 'AI-generated interpretation'}
          </p>
        )}
        {!isUser && message.dataNotice && (
          <p className="mt-2 border-t border-slate-200 pt-2 text-xs text-amber-800">
            {message.dataNotice}
          </p>
        )}
        {!isUser && message.sources?.length > 0 && (
          <p className="mt-2 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
            RentTrace sources: {message.sources.join(', ')}
          </p>
        )}
      </div>
    </div>
  );
}

export default function RentTraceChat({ selectedContext }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [configured, setConfigured] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const requestRef = useRef(null);
  const sendingRef = useRef(false);

  useEffect(() => () => requestRef.current?.abort(), []);

  useEffect(() => {
    if (!isOpen) return undefined;
    const controller = new AbortController();
    fetchChatStatus(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setConfigured(result.configured === true);
          setStatusMessage(result.message || '');
        }
      })
      .catch((statusError) => {
        if (statusError.name !== 'AbortError') {
          setConfigured(false);
          setStatusMessage('AI service status is unavailable. You can still try sending a message.');
        }
      });
    return () => controller.abort();
  }, [isOpen]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading, isOpen]);

  const clearChat = () => {
    requestRef.current?.abort();
    sendingRef.current = false;
    setMessages(INITIAL_MESSAGES);
    setDraft('');
    setError('');
    setLoading(false);
  };

  const submitMessage = async (prompt = draft) => {
    const message = prompt.trim();
    if (!message || sendingRef.current) return;
    sendingRef.current = true;

    const history = messages
      .filter((item) => item.role === 'user' || item.role === 'assistant')
      .slice(-10)
      .map(({ role, content }) => ({ role, content }));
    const userMessage = { role: 'user', content: message };
    const pendingMessages = [...messages, userMessage];
    setMessages(pendingMessages);
    setDraft('');
    setError('');
    setLoading(true);
    const controller = new AbortController();
    requestRef.current?.abort();
    requestRef.current = controller;

    try {
      const result = await sendChatMessage(
        { message, history, selectedContext },
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setMessages((current) => [...current, {
          role: 'assistant',
          content: result.answer,
          sources: result.sources,
          dataNotice: result.data_notice,
          answerKind: result.answer_kind,
        }]);
      }
    } catch (requestError) {
      if (requestError.name !== 'AbortError') {
        setError(requestError.message || 'RentTrace AI could not answer right now.');
      }
    } finally {
      if (!controller.signal.aborted) {
        sendingRef.current = false;
        setLoading(false);
        requestRef.current = null;
      }
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-[2500] flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {isOpen && (
        <section
          aria-label="RentTrace AI chat"
          className="flex h-[min(76dvh,680px)] w-[min(26rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-2xl ring-1 ring-slate-900/10"
        >
          <header className="flex items-center justify-between gap-3 bg-slate-900 px-4 py-3.5 text-white">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-lg" aria-hidden="true">✦</span>
              <div className="min-w-0">
                <h2 className="font-semibold">RentTrace AI</h2>
                <p className="flex items-center gap-1.5 text-xs text-slate-300">
                  <span className={`h-2 w-2 rounded-full ${configured ? 'bg-emerald-400' : configured === false ? 'bg-amber-400' : 'bg-slate-400'}`} aria-hidden="true" />
                  {configured === null ? 'Checking assistant…' : configured ? 'Ready · RentTrace data grounded' : 'Setup required'}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={clearChat}
                aria-label="Clear chat"
                title="Clear chat"
                className="min-h-10 rounded-lg px-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                aria-label="Minimize chat"
                className="h-10 w-10 rounded-lg text-lg text-slate-200 hover:bg-slate-700"
              >
                −
              </button>
            </div>
          </header>

          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3.5 sm:p-4" aria-live="polite">
            {messages.map((message, index) => (
              <ChatMessage key={`${index}-${message.role}`} message={message} />
            ))}
            {loading && (
              <div className="flex justify-start">
                <p role="status" className="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
                  RentTrace AI is analyzing available data…
                </p>
              </div>
            )}
            {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
            {!configured && statusMessage && (
              <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
                {statusMessage}
              </p>
            )}
          </div>

          {messages.length === 1 && (
            <div className="flex gap-2 overflow-x-auto border-t border-slate-200 bg-white px-3 py-2.5">
              {CHAT_QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  disabled={loading}
                  onClick={() => void submitMessage(action.prompt)}
                  className="min-h-9 shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-3 text-xs font-medium text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

          <form
            className="flex items-end gap-2 border-t border-slate-200 bg-white p-3"
            onSubmit={(event) => {
              event.preventDefault();
              void submitMessage();
            }}
          >
            <label htmlFor="renttrace-ai-message" className="sr-only">Message RentTrace AI</label>
            <textarea
              ref={textareaRef}
              id="renttrace-ai-message"
              rows={1}
              maxLength={1200}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about RentTrace data…"
              className="max-h-28 min-h-11 min-w-0 flex-1 resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
            />
            <button
              type="submit"
              disabled={loading || !draft.trim()}
              aria-label="Send message"
              className="min-h-11 shrink-0 rounded-xl bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-label={isOpen ? 'Minimize RentTrace AI chat' : 'Open RentTrace AI chat'}
        aria-expanded={isOpen}
        className="flex h-14 min-w-14 items-center justify-center gap-2 rounded-full bg-emerald-700 px-4 text-white shadow-xl transition hover:-translate-y-0.5 hover:bg-emerald-800 focus:outline-none focus:ring-4 focus:ring-emerald-200"
      >
        <span aria-hidden="true" className="text-xl">✦</span>
        <span className="text-sm font-semibold">RentTrace AI</span>
      </button>
    </div>
  );
}
