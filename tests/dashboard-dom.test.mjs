import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { JSDOM } from "jsdom";
import * as core from "../app/static/dashboard-core.mjs";

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(condition, message) {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    if (await condition()) return;
    await pause(25);
  }
  throw new Error(message);
}

test("dashboard DOM connects to real API: navigation, filters, create, copy, details, disable", async () => {
  const socket = createServer();
  socket.listen(0, "127.0.0.1");
  await once(socket, "listening");
  const port = socket.address().port;
  await new Promise((resolve) => socket.close(resolve));
  const origin = `http://127.0.0.1:${port}`;
  const processHandle = spawn(
    process.env.SHORTENER_TEST_PYTHON || "python",
    ["scripts/run_dashboard.py", "--port", String(port)],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  let logs = "";
  processHandle.stdout.on("data", (chunk) => (logs += chunk));
  processHandle.stderr.on("data", (chunk) => (logs += chunk));
  let dom;
  try {
    await until(async () => {
      try {
        return (await fetch(origin + "/ready")).ok;
      } catch {
        return false;
      }
    }, "Server did not start: " + logs);
    const html = await readFile(
      new URL("../app/static/index.html", import.meta.url),
      "utf8",
    );
    dom = new JSDOM(html, {
      url: origin + "/",
      runScripts: "outside-only",
      pretendToBeVisual: true,
    });
    const { window } = dom;
    window.__core = core;
    window.fetch = (path, options) => fetch(new URL(path, origin), options);
    window.HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
    window.HTMLDialogElement.prototype.close = function () {
      this.removeAttribute("open");
    };
    let copied;
    Object.defineProperty(window.navigator, "clipboard", {
      value: {
        writeText: async (text) => {
          copied = text;
        },
      },
    });
    const errors = [];
    window.addEventListener("error", (event) => errors.push(event.message));
    const source = await readFile(
      new URL("../app/static/dashboard.js", import.meta.url),
      "utf8",
    );
    window.eval(
      source.replace(
        /^import\s+\{[\s\S]*?\}\s+from\s+['"]\.\/dashboard-core\.mjs['"];?/,
        "const {linkStatus,destinationHost,fillDays,chartGeometry,nearestPoint,createPayload,paginationLabel,requestKey} = window.__core;",
      ),
    );
    const $ = (selector) => window.document.querySelector(selector);
    await until(
      () => $("#metric-links").textContent === "12",
      "Demo did not initialize",
    );
    $("#theme-toggle").click();
    assert.equal(window.document.documentElement.dataset.theme, "dark");
    assert.equal(window.localStorage.getItem("schwab-link-theme"), "dark");
    assert.match($("#theme-toggle").getAttribute("aria-label"), /light mode/);
    $("#theme-toggle").click();
    assert.equal(window.document.documentElement.dataset.theme, "light");
    assert.equal($("#demo-banner").hidden, false);
    assert.equal($("#metric-active").textContent, "9");
    assert.equal(window.document.querySelectorAll("#link-rows tr").length, 7);
    assert.ok($("#activity-chart svg"));
    const chart = $("#activity-chart svg");
    chart.getBoundingClientRect = () => ({
      left: 0,
      width: 640,
      top: 0,
      right: 640,
      bottom: 190,
      height: 190,
    });
    chart.dispatchEvent(
      new window.MouseEvent("pointermove", { bubbles: true, clientX: 320 }),
    );
    assert.equal($("#activity-chart .chart-tooltip").hidden, false);
    assert.match($("#activity-chart .chart-tooltip").textContent, /clicks/);
    chart.dispatchEvent(
      new window.MouseEvent("pointerleave", { bubbles: true }),
    );
    assert.equal($("#activity-chart .chart-tooltip").hidden, true);
    assert.equal($("#connect-dialog").open, false);
    $("#next-page").click();
    await until(
      () => $("#pagination-label").textContent.includes("8–12"),
      "Pagination did not advance",
    );
    $('[data-status="expired"]').click();
    await until(
      () => window.document.querySelectorAll("#link-rows tr").length === 1,
      "Expired filter failed",
    );
    assert.match($("#link-rows").textContent, /summer-campaign/);
    $('[data-status="all"]').click();
    $("#search").value = "no-such-link";
    $("#search").dispatchEvent(new window.Event("input"));
    await until(
      () =>
        !$("#empty-state").hidden &&
        $("#empty-state h3").textContent.includes("No links match"),
      "Search empty state failed",
    );
    $("#search").value = "";
    $("#search").dispatchEvent(new window.Event("input"));
    await until(() => $("#empty-state").hidden, "Search reset failed");
    $('[data-view="analytics"]').click();
    await until(
      () => window.document.body.classList.contains("view-analytics"),
      "Analytics navigation failed",
    );
    $("#chart-days").value = "7";
    $("#chart-days").dispatchEvent(new window.Event("change"));
    await until(
      () =>
        $("#activity-chart svg").getAttribute("aria-label").includes("7 days"),
      "Chart range failed",
    );
    $('[data-view="links"]').click();
    await until(
      () => window.document.body.classList.contains("view-links"),
      "Links navigation failed",
    );
    $(".create-trigger").click();
    assert.equal($("#create-dialog").open, true);
    $("#destination").value = "https://example.com/dom-integration";
    $("#alias").value = "dom-created";
    $("#create-form").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true }),
    );
    await until(
      () => $("#details-dialog").open && $("#details-content .detail-url"),
      "Create/details failed",
    );
    assert.equal($("#details-title").textContent, "dom-created");
    assert.match($("#details-content").textContent, /0All-time clicks/);
    $('#details-content [aria-label="Copy short link"]').click();
    await until(
      () => copied === origin + "/dom-created",
      "Clipboard action failed",
    );
    const redirected = await fetch(copied, { redirect: "manual" });
    assert.equal(redirected.status, 302);
    $('#details-content [aria-label="Disable link"]').click();
    assert.equal($("#disable-dialog").open, true);
    $("#disable-dialog .close-dialog").click();
    assert.equal($("#disable-dialog").open, false);
    assert.equal((await fetch(copied, { redirect: "manual" })).status, 302);
    $('#details-content [aria-label="Disable link"]').click();
    $("#confirm-disable").click();
    await until(
      () => $("#details-content .status-disabled"),
      "Disable did not refresh details",
    );
    assert.equal((await fetch(copied, { redirect: "manual" })).status, 410);
    assert.equal(
      (
        await (
          await fetch(origin + "/api/v1/links/dom-created/analytics")
        ).json()
      ).total_clicks,
      2,
    );
    assert.equal($("#metric-links").textContent, "13");
    assert.deepEqual(errors, []);
  } finally {
    if (dom) dom.window.close();
    const exited = once(processHandle, "exit");
    processHandle.kill("SIGTERM");
    await exited;
  }
});
