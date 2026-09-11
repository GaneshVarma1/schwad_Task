import test from "node:test";
import assert from "node:assert/strict";
import {
  chartGeometry,
  fillDays,
  linkStatus,
  createPayload,
  paginationLabel,
  destinationHost,
  nearestPoint,
  requestKey,
} from "../app/static/dashboard-core.mjs";

test("chart handles an empty data set and all-zero counts without NaN", () => {
  assert.equal(chartGeometry([]).points.length, 0);
  const data = chartGeometry([{ date: "2026-01-01", clicks: 0 }]);
  assert.ok(Number.isFinite(data.points[0].x));
  assert.equal(data.points[0].y, data.baseline);
  assert.ok(data.ceiling > 0);
});
test("chart scales across all points without clipping the maximum", () => {
  const data = chartGeometry([
    { date: "a", clicks: 2 },
    { date: "b", clicks: 950 },
    { date: "c", clicks: 8 },
  ]);
  assert.ok(data.ceiling >= 950);
  assert.ok(data.points.every((p) => p.y >= data.top && p.y <= data.baseline));
  assert.equal(data.points[0].x, data.left);
  assert.equal(data.points.at(-1).x, data.width - data.right);
});
test("chart hover resolves the nearest data point", () => {
  const points = [
    { x: 10, clicks: 2 },
    { x: 50, clicks: 9 },
    { x: 90, clicks: 4 },
  ];
  assert.equal(nearestPoint(points, 62).clicks, 9);
  assert.equal(nearestPoint(points, 88).clicks, 4);
  assert.equal(nearestPoint([], 20), null);
});
test("daily series fills missing days and respects UTC month boundaries", () => {
  const days = fillDays(
    [
      { date: "2026-02-28", clicks: 9 },
      { date: "2025-01-01", clicks: 100 },
    ],
    3,
    new Date("2026-03-01T23:00:00Z"),
  );
  assert.deepEqual(days, [
    { date: "2026-02-27", clicks: 0 },
    { date: "2026-02-28", clicks: 9 },
    { date: "2026-03-01", clicks: 0 },
  ]);
});
test("disabled takes priority and exact expiration is inactive", () => {
  const now = Date.parse("2026-03-01T00:00:00Z");
  assert.equal(
    linkStatus({ disabled: false, expires_at: null }, now),
    "active",
  );
  assert.equal(
    linkStatus({ disabled: false, expires_at: "2026-03-01T00:00:00Z" }, now),
    "expired",
  );
  assert.equal(
    linkStatus({ disabled: true, expires_at: "2026-03-01T00:00:00Z" }, now),
    "disabled",
  );
});
test("creation omits empty options, serializes time, and rejects past expiration", () => {
  assert.deepEqual(createPayload(" https://example.com ", "", ""), {
    url: "https://example.com",
  });
  assert.deepEqual(
    createPayload(
      "https://example.com",
      " my-link ",
      "2027-01-01T12:00:00Z",
      0,
    ),
    {
      url: "https://example.com",
      custom_alias: "my-link",
      expires_at: "2027-01-01T12:00:00.000Z",
    },
  );
  assert.throws(
    () => createPayload("https://example.com", "", "2020-01-01", Date.now()),
    /future/,
  );
  assert.throws(
    () => createPayload("https://example.com", "", "garbage"),
    /future/,
  );
});
test("pagination accurately describes empty and partial pages", () => {
  assert.equal(paginationLabel(0, 0, 7), "No links to display");
  assert.equal(paginationLabel(12, 7, 7), "Showing 8–12 of 12 links");
});
test("destination host extraction does not assume valid input", () => {
  assert.equal(destinationHost("https://www.example.com/path"), "example.com");
  assert.equal(destinationHost("not a url"), "Unknown destination");
});
test("request key uses randomUUID when the context provides it", () => {
  const key = requestKey({
    randomUUID: () => "11111111-2222-3333-4444-555555555555",
  });
  assert.equal(key, "11111111-2222-3333-4444-555555555555");
});
test("request key falls back when randomUUID is missing outside a secure context", () => {
  const source = {
    getRandomValues: (bytes) => {
      bytes.forEach((_, index) => {
        bytes[index] = index;
      });
      return bytes;
    },
  };
  assert.equal(requestKey(source), "000102030405060708090a0b0c0d0e0f");
});
test("request key always satisfies the server Idempotency-Key contract", () => {
  for (const source of [undefined, {}, { getRandomValues: undefined }]) {
    const key = requestKey(source);
    assert.match(key, /^[A-Za-z0-9._:-]+$/);
    assert.ok(key.length >= 8 && key.length <= 128);
  }
  assert.notEqual(requestKey({}), requestKey({}));
});
