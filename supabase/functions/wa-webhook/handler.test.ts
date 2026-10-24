// Run: node --experimental-strip-types --test supabase/functions/wa-webhook/handler.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle, type Store } from "./handler.ts";

const env = { verifyToken: "vt", appSecret: "app-secret", relaySecret: "relay" };

function memStore(): Store & { rows: any[] } {
  const rows: any[] = [];
  return {
    rows,
    async insert(r) { rows.push({ id: rows.length + 1, ...r }); },
    async pending(approvalId) { return rows.filter((r) => r.approval_id === approvalId); },
  };
}

async function sign(body: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)));
  return "sha256=" + [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const buttonReply = (id: string) => JSON.stringify({ entry: [{ changes: [{ value: { messages: [
  { from: "15550001", type: "interactive", interactive: { type: "button_reply", button_reply: { id, title: "Yes" } } },
] } }] }] });

const templateReply = (payload: string) => JSON.stringify({ entry: [{ changes: [{ value: { messages: [
  { from: "15550001", type: "button", button: { payload, text: "No" } },
] } }] }] });

test("verification handshake echoes challenge", async () => {
  const res = await handle(new Request("https://x/wa-webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=42"), env, memStore());
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "42");
});

test("verification with wrong token is 403", async () => {
  const res = await handle(new Request("https://x/wa-webhook?hub.mode=subscribe&hub.verify_token=bad&hub.challenge=42"), env, memStore());
  assert.equal(res.status, 403);
});

test("rejects bad signature (401)", async () => {
  const store = memStore();
  const res = await handle(new Request("https://x/wa-webhook", { method: "POST", body: buttonReply("a1:yes"), headers: { "x-hub-signature-256": "sha256=00" } }), env, store);
  assert.equal(res.status, 401);
  assert.equal(store.rows.length, 0);
});

test("stores interactive button reply", async () => {
  const store = memStore();
  const body = buttonReply("a1:yes");
  const res = await handle(new Request("https://x/wa-webhook", { method: "POST", body, headers: { "x-hub-signature-256": await sign(body, "app-secret") } }), env, store);
  assert.equal(res.status, 200);
  assert.deepEqual(store.rows.map((r) => [r.approval_id, r.answer]), [["a1", "yes"]]);
});

test("stores template quick-reply payload", async () => {
  const store = memStore();
  const body = templateReply("a2:no");
  await handle(new Request("https://x/wa-webhook", { method: "POST", body, headers: { "x-hub-signature-256": await sign(body, "app-secret") } }), env, store);
  assert.deepEqual(store.rows.map((r) => [r.approval_id, r.answer]), [["a2", "no"]]);
});

test("ignores unrelated messages", async () => {
  const store = memStore();
  const body = JSON.stringify({ entry: [{ changes: [{ value: { messages: [{ type: "text", text: { body: "hi" } }] } }] }] });
  const res = await handle(new Request("https://x/wa-webhook", { method: "POST", body, headers: { "x-hub-signature-256": await sign(body, "app-secret") } }), env, store);
  assert.equal(res.status, 200);
  assert.equal(store.rows.length, 0);
});

test("pending requires bearer", async () => {
  const res = await handle(new Request("https://x/wa-webhook/pending?approval_id=a1"), env, memStore());
  assert.equal(res.status, 401);
});

test("pending returns rows for approval id", async () => {
  const store = memStore();
  await store.insert({ approval_id: "a1", answer: "yes", from_number: "1" });
  await store.insert({ approval_id: "b2", answer: "no", from_number: "1" });
  const res = await handle(new Request("https://x/wa-webhook/pending?approval_id=a1", { headers: { authorization: "Bearer relay" } }), env, store);
  const rows = await res.json();
  assert.deepEqual(rows.map((r: any) => r.answer), ["yes"]);
});
