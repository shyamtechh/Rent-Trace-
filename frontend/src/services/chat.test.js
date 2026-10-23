import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CHAT_QUICK_ACTIONS,
  CHAT_WELCOME_MESSAGE,
  fetchChatStatus,
  sendChatMessage,
} from './chat.js';

test('provides the requested welcome message and quick prompts', () => {
  assert.match(CHAT_WELCOME_MESSAGE, /^Hi! I’m RentTrace AI\./);
  assert.deepEqual(
    CHAT_QUICK_ACTIONS.map((action) => action.label),
    ['Area Analysis', 'Rental Analysis', 'Price Trends', 'Compare Areas', 'Explain This', 'Forecast'],
  );
});

test('checks assistant status through the authenticated backend route', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return new Response(JSON.stringify({
      configured: true,
      message: 'RentTrace AI is ready.',
    }), { status: 200 });
  };
  try {
    const result = await fetchChatStatus();
    assert.equal(requestedUrl, '/api/chat/status');
    assert.equal(result.configured, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('sends bounded conversation and selected-map context to the backend', async () => {
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return new Response(JSON.stringify({
      answer: 'Rent data is unavailable.',
      sources: [],
      localities: ['Gachibowli'],
      data_notice: null,
      answer_kind: 'renttrace_data',
    }), { status: 200 });
  };
  try {
    const result = await sendChatMessage({
      message: 'What about this area?',
      history: Array.from({ length: 12 }, (_, index) => ({
        role: index % 2 ? 'assistant' : 'user',
        content: `Message ${index}`,
      })),
      selectedContext: {
        locality_name: 'Gachibowli',
        latitude: 17.44,
        longitude: 78.39,
        polygon_area_square_feet: 2450,
      },
    });
    const body = JSON.parse(request.options.body);
    assert.equal(request.url, '/api/chat');
    assert.equal(body.history.length, 6);
    assert.equal(body.history[0].content, 'Message 6');
    assert.equal(body.selected_context.locality_name, 'Gachibowli');
    assert.equal(result.answer, 'Rent data is unavailable.');
    assert.equal(result.answer_kind, 'renttrace_data');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('surfaces provider errors and rejects malformed assistant responses', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: 'RentTrace AI is not configured.' }),
      { status: 503 },
    );
    await assert.rejects(sendChatMessage({ message: 'hello', history: [] }), /not configured/i);

    globalThis.fetch = async () => new Response(
      JSON.stringify({ answer: 1, sources: null }),
      { status: 200 },
    );
    await assert.rejects(sendChatMessage({ message: 'hello', history: [] }), /invalid response/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
