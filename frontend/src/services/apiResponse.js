function responseStatus(response) {
  return `${response.status}${response.statusText ? ` ${response.statusText}` : ''}`;
}

function getErrorDetail(data) {
  const detail = data?.detail ?? data?.message;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item?.msg === 'string' ? item.msg : JSON.stringify(item)))
      .join('; ');
  }
  if (detail != null) {
    return JSON.stringify(detail);
  }
  return null;
}

export async function readApiResponse(response, action, { allowNull = false } = {}) {
  const body = await response.text();
  let data = null;
  let invalidJson = false;

  if (body.trim()) {
    try {
      data = JSON.parse(body);
    } catch {
      invalidJson = true;
    }
  }

  if (!response.ok) {
    const detail = invalidJson ? null : getErrorDetail(data);
    const message = detail || body.trim();
    if (message) {
      throw new Error(message);
    }

    throw new Error(`${action} failed (HTTP ${responseStatus(response)}): the server returned an empty response.`);
  }

  if (invalidJson) {
    throw new Error(
      `${action} returned a non-JSON response (HTTP ${responseStatus(response)}): ${body.trim()}`,
    );
  }

  if (allowNull && body.trim() === 'null' && data === null) {
    return null;
  }

  if (data == null || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`${action} returned an empty or invalid JSON response (HTTP ${responseStatus(response)}).`);
  }

  return data;
}
