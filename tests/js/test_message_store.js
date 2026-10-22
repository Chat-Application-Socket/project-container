// Unit tests for static/messages.js (BL-08: messages appear in order, once).
// Run directly with:  node tests/js/test_message_store.js
// Also run by pytest through tests/test_message_order.py.
//
// Maps to Test Plan REQ-12 (message order) and BL-08 acceptance criteria.

"use strict";

const assert = require("assert");
const path = require("path");
const { MessageStore } = require(path.join(__dirname, "..", "..", "static", "messages.js"));

const tests = [];
function test(name, fn) {
  tests.push({ name, fn });
}

function contents(store) {
  return store.getOrdered().map((m) => m.content);
}

test("messages without seq keep arrival order", () => {
  const store = new MessageStore();
  assert.strictEqual(store.add({ id: "a", content: "first" }), 0);
  assert.strictEqual(store.add({ id: "b", content: "second" }), 1);
  assert.strictEqual(store.add({ id: "c", content: "third" }), 2);
  assert.deepStrictEqual(contents(store), ["first", "second", "third"]);
});

test("in-order seq messages are appended", () => {
  const store = new MessageStore();
  [1, 2, 3, 4].forEach((seq) => {
    assert.strictEqual(store.add({ id: "m" + seq, seq: seq, content: "s" + seq }), seq - 1);
  });
  assert.deepStrictEqual(contents(store), ["s1", "s2", "s3", "s4"]);
});

test("a late message is inserted at its seq position", () => {
  const store = new MessageStore();
  store.add({ id: "1", seq: 1, content: "one" });
  store.add({ id: "3", seq: 3, content: "three" });
  store.add({ id: "4", seq: 4, content: "four" });
  const index = store.add({ id: "2", seq: 2, content: "two" });
  assert.strictEqual(index, 1);
  assert.deepStrictEqual(contents(store), ["one", "two", "three", "four"]);
});

test("fully reversed delivery still ends up sorted by seq", () => {
  const store = new MessageStore();
  [5, 4, 3, 2, 1].forEach((seq) => store.add({ id: "x" + seq, seq: seq, content: String(seq) }));
  assert.deepStrictEqual(contents(store), ["1", "2", "3", "4", "5"]);
});

test("duplicate id is ignored and not shown twice", () => {
  const store = new MessageStore();
  assert.strictEqual(store.add({ id: "dup", seq: 1, content: "hello" }), 0);
  assert.strictEqual(store.add({ id: "dup", seq: 1, content: "hello" }), -1);
  assert.strictEqual(store.size(), 1);
});

test("numeric and string ids are treated the same", () => {
  const store = new MessageStore();
  store.add({ id: 7, content: "a" });
  assert.strictEqual(store.add({ id: "7", content: "a" }), -1);
});

test("messages without id are never de-duplicated", () => {
  const store = new MessageStore();
  store.add({ content: "same" });
  store.add({ content: "same" });
  assert.strictEqual(store.size(), 2);
});

test("invalid events are ignored without throwing", () => {
  const store = new MessageStore();
  [null, undefined, "text", 42, true].forEach((bad) => {
    assert.strictEqual(store.add(bad), -1);
  });
  assert.strictEqual(store.size(), 0);
});

test("message without seq after seq messages is appended", () => {
  const store = new MessageStore();
  store.add({ id: "1", seq: 1, content: "one" });
  store.add({ id: "2", seq: 2, content: "two" });
  assert.strictEqual(store.add({ id: "n", content: "no-seq" }), 2);
});

test("getOrdered returns a copy", () => {
  const store = new MessageStore();
  store.add({ id: "1", content: "one" });
  store.getOrdered().pop();
  assert.strictEqual(store.size(), 1);
});

test("clear empties messages and forgets seen ids", () => {
  const store = new MessageStore();
  store.add({ id: "1", content: "one" });
  store.clear();
  assert.strictEqual(store.size(), 0);
  assert.strictEqual(store.add({ id: "1", content: "one" }), 0);
});

test("100 messages from 3 senders keep one total order", () => {
  const store = new MessageStore();
  const senders = ["alice", "bob", "carol"];
  for (let seq = 1; seq <= 100; seq += 1) {
    store.add({ id: "id" + seq, seq: seq, sender: senders[seq % 3], content: "m" + seq });
  }
  const seqs = store.getOrdered().map((m) => m.seq);
  for (let i = 1; i < seqs.length; i += 1) {
    assert.ok(seqs[i - 1] < seqs[i], "seq must increase");
  }
});

let failed = 0;
tests.forEach(({ name, fn }) => {
  try {
    fn();
    console.log("ok   - " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL - " + name);
    console.log("       " + (err && err.message ? err.message : err));
  }
});

console.log(`\n${tests.length - failed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
