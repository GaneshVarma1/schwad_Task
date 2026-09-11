export function linkStatus(link, now = Date.now()) {
  if (link.disabled) return "disabled";
  return link.expires_at && Date.parse(link.expires_at) <= now
    ? "expired"
    : "active";
}
export function destinationHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Unknown destination";
  }
}
export function fillDays(daily, days = 30, today = new Date()) {
  const end = new Date(
    Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()),
  );
  const counts = new Map(daily.map((point) => [point.date, point.clicks]));
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(end.getTime() - (days - 1 - index) * 86400000)
      .toISOString()
      .slice(0, 10);
    return { date, clicks: counts.get(date) || 0 };
  });
}
export function chartGeometry(daily) {
  const width = 640,
    height = 190,
    left = 42,
    right = 15,
    top = 10,
    bottom = 30;
  const maxValue = Math.max(0, ...daily.map((item) => item.clicks));
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, maxValue)));
  const ceiling = Math.max(4, Math.ceil(maxValue / magnitude) * magnitude);
  const plotWidth = width - left - right,
    plotHeight = height - top - bottom;
  const points = daily.map((item, index) => ({
    ...item,
    x:
      left +
      (daily.length <= 1
        ? plotWidth / 2
        : (index / (daily.length - 1)) * plotWidth),
    y: top + plotHeight * (1 - item.clicks / ceiling),
  }));
  return {
    width,
    height,
    left,
    right,
    top,
    bottom,
    ceiling,
    points,
    baseline: height - bottom,
  };
}
export function nearestPoint(points, x) {
  if (!points.length) return null;
  return points.reduce((closest, point) =>
    Math.abs(point.x - x) < Math.abs(closest.x - x) ? point : closest,
  );
}
export function requestKey(source = globalThis.crypto) {
  // crypto.randomUUID is restricted to secure contexts, so it is absent when the
  // dashboard is served over plain HTTP from anything but loopback. getRandomValues
  // carries no such restriction, and an idempotency key needs uniqueness rather than
  // unpredictability. Math.random is a last resort that keeps creation available.
  if (typeof source?.randomUUID === "function") return source.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof source?.getRandomValues === "function") {
    source.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}
export function createPayload(url, alias, expiry, now = Date.now()) {
  const payload = { url: url.trim() };
  if (alias.trim()) payload.custom_alias = alias.trim();
  if (expiry) {
    const date = new Date(expiry);
    if (!Number.isFinite(date.getTime()) || date.getTime() <= now) {
      throw new Error("Choose an expiration date in the future.");
    }
    payload.expires_at = date.toISOString();
  }
  return payload;
}
export function paginationLabel(total, offset, limit) {
  if (!total) return "No links to display";
  return `Showing ${offset + 1}–${Math.min(offset + limit, total)} of ${total} links`;
}
