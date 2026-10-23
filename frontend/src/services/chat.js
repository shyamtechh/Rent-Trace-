import { readApiResponse } from './apiResponse.js';

export const CHAT_WELCOME_MESSAGE = 'Hi! I’m RentTrace AI. I can help you understand Hyderabad’s housing prices, rental trends, locality comparisons, historical changes, and other RentTrace insights. Ask me anything about the data.';

export const CHAT_QUICK_ACTIONS = [
  { label: 'Area Analysis', prompt: 'Analyze the selected area.' },
  { label: 'Rental Analysis', prompt: 'Summarize the rental data for the selected area.' },
  { label: 'Price Trends', prompt: 'Explain the historical price trend for the selected area.' },
  { label: 'Compare Areas', prompt: 'Which localities are available to compare with this area?' },
  { label: 'Explain This', prompt: 'Explain the selected area and available RentTrace data simply.' },
  { label: 'Forecast', prompt: 'Explain the available forecast for the selected area.' },
];

export async function fetchChatStatus(signal) {
  const response = await fetch('/api/chat/status', { signal });
  return readApiResponse(response, 'Check RentTrace AI status');
}

export async function sendChatMessage({ message, history, selectedContext }, signal) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history: history.slice(-6).map(({ role, content }) => ({
        role,
        content: content.slice(0, 800),
      })),
      selected_context: selectedContext ?? null,
    }),
    signal,
  });
  const payload = await readApiResponse(response, 'Ask RentTrace AI');
  if (
    typeof payload.answer !== 'string'
    || !Array.isArray(payload.sources)
    || !Array.isArray(payload.localities)
    || !['renttrace_data', 'ai_interpretation', 'data_unavailable'].includes(payload.answer_kind)
    || (payload.data_notice !== null && typeof payload.data_notice !== 'string')
  ) {
    throw new Error('RentTrace AI returned an invalid response.');
  }
  return payload;
}
