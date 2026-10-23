import assert from 'node:assert/strict';
import test from 'node:test';
import { readApiResponse } from './apiResponse.js';

test('reads a successful JSON response', async () => {
  const result = await readApiResponse(
    new Response(JSON.stringify({ message: 'Login successful' }), { status: 200 }),
    'Login',
  );
  assert.deepEqual(result, { message: 'Login successful' });
});

test('preserves a JSON API error detail', async () => {
  await assert.rejects(
    readApiResponse(
      new Response(JSON.stringify({ detail: 'Invalid email or password.' }), { status: 401 }),
      'Login',
    ),
    { message: 'Invalid email or password.' },
  );
});

test('preserves a non-JSON server error body', async () => {
  await assert.rejects(
    readApiResponse(new Response('upstream unavailable', { status: 502 }), 'Login'),
    { message: 'upstream unavailable' },
  );
});

test('includes the malformed response body when a successful response is not JSON', async () => {
  await assert.rejects(
    readApiResponse(new Response('upstream diagnostic', { status: 200 }), 'Login'),
    { message: 'Login returned a non-JSON response (HTTP 200): upstream diagnostic' },
  );
});

test('reports an empty error response with its HTTP status', async () => {
  await assert.rejects(
    readApiResponse(new Response(null, { status: 502 }), 'Login'),
    { message: /Login failed \(HTTP 502\).*empty response/ },
  );
});

test('reports an empty successful response as a protocol error', async () => {
  await assert.rejects(
    readApiResponse(new Response(null, { status: 200 }), 'Login'),
    { message: /Login returned an empty or invalid JSON response \(HTTP 200\)/ },
  );
});
