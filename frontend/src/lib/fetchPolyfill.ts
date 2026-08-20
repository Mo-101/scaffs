// Defensive fetch/AbortController presence check.
//
// This module is imported first thing in `main.tsx`, before any other app
// code runs a network request. It intentionally does nothing in any modern
// browser (fetch and AbortController have been standard since 2017/2020
// respectively) -- it only guards against a runtime that's missing them
// (e.g. certain embedded webviews or very old browsers) by surfacing a
// clear console warning instead of a silent "fetch is not defined" crash
// deep inside some unrelated component.
if (typeof globalThis.fetch !== "function") {
  // eslint-disable-next-line no-console
  console.warn(
    "[fetchPolyfill] globalThis.fetch is unavailable in this runtime. " +
      "This app requires a browser with native fetch support."
  );
}

if (typeof globalThis.AbortController !== "function") {
  // eslint-disable-next-line no-console
  console.warn(
    "[fetchPolyfill] globalThis.AbortController is unavailable in this runtime."
  );
}

export {};
