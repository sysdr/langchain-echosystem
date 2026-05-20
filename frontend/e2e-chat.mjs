/**
 * Quick UI smoke test: open chat, send message, wait for assistant reply.
 * Run: node e2e-chat.mjs
 */
import { chromium } from "playwright";

const BASE = process.env.UI_URL || "http://127.0.0.1:5173";
const PROMPT = "Reply with exactly: UI test OK";
const TIMEOUT_MS = 90_000;

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto(BASE, { waitUntil: "networkidle", timeout: 30_000 });

    const textarea = page.locator("textarea");
    await textarea.waitFor({ state: "visible", timeout: 15_000 });

    await page.waitForFunction(
      () => !document.querySelector('button.primary')?.hasAttribute('disabled') ||
        document.querySelector('.status')?.textContent?.includes('…'),
      { timeout: 15_000 },
    ).catch(() => {});

    await textarea.fill(PROMPT);
    const sendBtn = page.getByRole("button", { name: /^Send$/i });
    await sendBtn.waitFor({ state: "visible", timeout: 5_000 });
    if (await sendBtn.isDisabled()) {
      const banner = await page.locator(".banner").textContent().catch(() => "");
      throw new Error(`Send still disabled after input. ${banner?.slice(0, 200)}`);
    }
    await sendBtn.click();

    const assistantBubble = page.locator(".bubble.assistant").last();
    await assistantBubble.waitFor({ state: "visible", timeout: TIMEOUT_MS });

    await page.waitForFunction(
      () => {
        const el = document.querySelector(".bubble.assistant:last-of-type");
        if (!el) return false;
        const text = el.textContent || "";
        return text.length > 10 && !el.classList.contains("streaming");
      },
      { timeout: TIMEOUT_MS },
    );

    const reply = (await assistantBubble.textContent())?.trim() || "";
    console.log("PASS: Assistant replied");
    console.log("Reply preview:", reply.slice(0, 300));

    const err = await page.locator(".error-bar").textContent().catch(() => null);
    if (err?.trim()) {
      throw new Error(`UI error bar: ${err.trim()}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
