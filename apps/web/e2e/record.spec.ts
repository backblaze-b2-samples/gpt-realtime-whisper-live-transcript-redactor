import { test, expect } from "@playwright/test";

/**
 * /record smoke test with a fully mocked transport.
 *
 * The real flow is mic -> AudioWorklet -> WebSocket -> OpenAI Realtime.
 * In the test environment we cannot grant mic permission, so we stub:
 *  - `navigator.mediaDevices.getUserMedia` + `AudioWorkletNode` so the
 *    audio-capture layer accepts and ignores us
 *  - `window.WebSocket` so the page sees a fake socket that we drive
 *    through the expected start -> delta -> segment -> finalized flow
 *
 * The `POST /sessions` API call is intercepted via `page.route()`.
 */

const FAKE_SESSION_ID = "20260528103045-fakeid12";

test.describe("/record with mocked WebSocket", () => {
  test.beforeEach(async ({ page }) => {
    // 1) Stub getUserMedia + AudioWorkletNode so startCapture() succeeds
    //    without a real microphone. The worklet's audio-worklet.js module
    //    fetch is also no-op'd by replacing `audioWorklet.addModule`.
    await page.addInitScript(() => {
      type FakeTrack = { stop(): void };
      const fakeStream = {
        getTracks: (): FakeTrack[] => [{ stop() {} }],
      } as unknown as MediaStream;

      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          getUserMedia: async () => fakeStream,
        },
      });

      // Stub AudioContext + AudioWorkletNode minimally enough that
      // startCapture's graph wiring runs without exceptions.
      class FakeAudioWorklet {
        async addModule() {
          /* noop */
        }
      }
      class FakeAudioNode {
        connect() {
          return this;
        }
        disconnect() {
          /* noop */
        }
        port = { onmessage: null as ((e: MessageEvent) => void) | null };
        gain = { value: 0 };
      }
      class FakeAudioContext {
        audioWorklet = new FakeAudioWorklet();
        destination = new FakeAudioNode();
        createMediaStreamSource() {
          return new FakeAudioNode();
        }
        createGain() {
          return new FakeAudioNode();
        }
        async close() {
          /* noop */
        }
      }
      // @ts-expect-error overriding for test
      window.AudioContext = FakeAudioContext;
      // @ts-expect-error overriding for test
      window.AudioWorkletNode = class extends FakeAudioNode {};

      // 2) WebSocket stub — exposes window.__lastFakeSocket so the test
      //    can drive messages from the outside.
      class FakeWebSocket extends EventTarget {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;
        readyState = FakeWebSocket.CONNECTING;
        binaryType: BinaryType = "arraybuffer";
        url: string;
        onopen: ((this: WebSocket, ev: Event) => void) | null = null;
        onmessage: ((this: WebSocket, ev: MessageEvent) => void) | null = null;
        onerror: ((this: WebSocket, ev: Event) => void) | null = null;
        onclose: ((this: WebSocket, ev: CloseEvent) => void) | null = null;

        constructor(url: string) {
          super();
          this.url = url;
          // Expose the most recent instance so the test can poke it.
          // @ts-expect-error attaching for test inspection
          window.__lastFakeSocket = this;
          // Open asynchronously so the page's awaited onopen resolves.
          setTimeout(() => {
            this.readyState = FakeWebSocket.OPEN;
            this.onopen?.call(this as unknown as WebSocket, new Event("open"));
          }, 0);
        }

        send(_data: unknown) {
          // @ts-expect-error capture for assertions
          (window.__sentToFakeSocket ||= []).push(_data);
        }

        close() {
          this.readyState = FakeWebSocket.CLOSED;
          this.onclose?.call(
            this as unknown as WebSocket,
            new CloseEvent("close"),
          );
        }

        // Test helper — pushes a server-to-client message into the
        // page's onmessage handler.
        __push(payload: unknown) {
          const data =
            typeof payload === "string" ? payload : JSON.stringify(payload);
          this.onmessage?.call(
            this as unknown as WebSocket,
            new MessageEvent("message", { data }),
          );
        }
      }
      // @ts-expect-error replacing the real WebSocket
      window.WebSocket = FakeWebSocket;
    });

    // 3) Mock the POST /sessions response so the page can start the WS.
    await page.route("**/sessions", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: FAKE_SESSION_ID,
          created_at: new Date().toISOString(),
          storage_mode: "originals_stored",
          redaction_modes: ["pii", "secrets", "glossary"],
          model: "gpt-realtime-whisper",
        }),
      });
    });
  });

  test("renders transcript delta + redaction chip from mocked socket", async ({
    page,
  }) => {
    await page.goto("/record");
    await page.getByRole("button", { name: /start recording/i }).click();

    // Wait for the WS to be constructed.
    await page.waitForFunction(
      // @ts-expect-error test-only globals
      () => Boolean(window.__lastFakeSocket?.onmessage),
    );

    // Push a transcript delta — the UI should render it as italic in-flight text.
    await page.evaluate(() => {
      // @ts-expect-error test-only globals
      window.__lastFakeSocket.__push({
        type: "delta",
        text: "hello there",
      });
    });
    await expect(page.getByText("hello there")).toBeVisible();

    // Push a completed segment with a high-severity PII detection.
    await page.evaluate(() => {
      // @ts-expect-error test-only globals
      window.__lastFakeSocket.__push({
        type: "segment",
        segment: {
          index: 0,
          started_at_ms: 0,
          ended_at_ms: 1500,
          redacted_text: "my ssn is [REDACTED:SSN]",
        },
        detections: [
          {
            segment_index: 0,
            start: 11,
            end: 22,
            type: "ssn",
            severity: "high",
            source: "pii",
            replacement: "[REDACTED:SSN]",
          },
        ],
      });
    });
    await expect(
      page.getByText("my ssn is [REDACTED:SSN]"),
    ).toBeVisible();
    // The severity chip is rendered as the detection type label ("ssn"),
    // colored by severity. We assert presence of the label here; color
    // checks live in component-level tests.
    await expect(page.getByText("ssn", { exact: true })).toBeVisible();

    // Drive the stop button -> the page sends {type:"stop"} on the socket.
    await page.getByRole("button", { name: /^stop$/i }).click();

    // Push the finalized event so the page settles back to idle state.
    await page.evaluate((sid) => {
      // @ts-expect-error test-only globals
      window.__lastFakeSocket.__push({
        type: "finalized",
        session_id: sid,
        segment_count: 1,
        detection_count: 1,
      });
    }, FAKE_SESSION_ID);

    // The "Start recording" CTA should reappear.
    await expect(
      page.getByRole("button", { name: /start recording/i }),
    ).toBeVisible();
  });
});
