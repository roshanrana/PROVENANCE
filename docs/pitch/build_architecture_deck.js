const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.author = "Roshan Rana";
pres.title = "PROVENANCE — AI Systems Architecture Review";

// Palette
const NAVY = "14213D", INK = "1B2A41", WHITE = "FFFFFF", ICE = "DCE7F5", MINT = "2EC4B6",
  GOLD = "F2B134", MUTED = "6B7A90", CARD = "F3F6FA", LINE = "C9D3E0", CARD_D = "1C2B4F", RED = "D64550";
const HF = "Cambria", BF = "Calibri";
const ASSETS = "C:/Code-Central/PROVENANCE/docs/assets/";

let n = 0;
function base(title, kicker) {
  const s = pres.addSlide();
  n += 1;
  s.background = { color: WHITE };
  if (kicker) s.addText(kicker.toUpperCase(), { x: 0.5, y: 0.28, w: 6, h: 0.25, fontFace: BF, fontSize: 10, bold: true, color: MINT, charSpacing: 2, isTextBox: true, margin: 0 });
  s.addText(title, { x: 0.5, y: 0.5, w: 9, h: 0.6, fontFace: HF, fontSize: 26, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  s.addText(`PROVENANCE · AI Systems Architecture Review · ${n}`, { x: 0.5, y: 5.25, w: 9, h: 0.25, fontFace: BF, fontSize: 8, color: MUTED, isTextBox: true, margin: 0 });
  return s;
}
function dark(title, sub) {
  const s = pres.addSlide();
  n += 1;
  s.background = { color: NAVY };
  s.addText(title, { x: 0.6, y: 1.9, w: 8.8, h: 0.9, fontFace: HF, fontSize: 34, bold: true, color: WHITE, isTextBox: true, margin: 0 });
  if (sub) s.addText(sub, { x: 0.6, y: 2.85, w: 8.8, h: 0.6, fontFace: BF, fontSize: 15, italic: true, color: ICE, isTextBox: true, margin: 0 });
  return s;
}
function card(s, x, y, w, h, fill = CARD, line = LINE) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line, width: 0.75 }, rectRadius: 0.06 });
}
function box(s, x, y, w, h, title, body, opt = {}) {
  const fill = opt.fill || CARD, tcol = opt.tcol || NAVY, bcol = opt.bcol || INK, line = opt.line || LINE;
  card(s, x, y, w, h, fill, line);
  s.addText(title, { x: x + 0.1, y: y + 0.06, w: w - 0.2, h: 0.28, fontFace: BF, fontSize: opt.ts || 11, bold: true, color: tcol, isTextBox: true, margin: 0 });
  if (body) s.addText(body, { x: x + 0.1, y: y + 0.34, w: w - 0.2, h: h - 0.4, fontFace: BF, fontSize: opt.bs || 8.5, color: bcol, isTextBox: true, margin: 0, valign: "top" });
}
function arrow(s, x1, y1, x2, y2, color = MUTED, w = 1.25) {
  const flipH = x2 < x1, flipV = y2 < y1;
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.01, h: Math.abs(y2 - y1) || 0.01, line: { color, width: w, endArrowType: "triangle" }, flipH, flipV });
}
function bullets(s, items, x, y, w, h, fs = 11, color = INK) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })), { x, y, w, h, fontFace: BF, fontSize: fs, color, isTextBox: true, margin: 0, paraSpaceAfter: 4, valign: "top" });
}
function table(s, rows, x, y, w, colW, fs = 8.5, rowH) {
  const data = rows.map((r, i) => r.map((c) => ({ text: c, options: i === 0 ? { bold: true, color: WHITE, fill: { color: NAVY }, fontSize: fs } : { fontSize: fs, color: INK } })));
  s.addTable(data, { x, y, w, colW, fontFace: BF, border: { type: "solid", pt: 0.5, color: LINE }, autoPage: false, rowH });
}
function imgFit(s, path, x, y, maxW, maxH, pw, ph) {
  const r = Math.min(maxW / pw, maxH / ph);
  const w = pw * r, h = ph * r;
  s.addImage({ path, x: x + (maxW - w) / 2, y, w, h });
  return { w, h };
}
function caption(s, text, x, y, w) {
  s.addText(text, { x, y, w, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 1 Title
{
  const s = pres.addSlide(); n += 1; s.background = { color: NAVY };
  s.addText("PROVENANCE", { x: 0.6, y: 1.35, w: 8, h: 0.9, fontFace: HF, fontSize: 44, bold: true, color: WHITE, isTextBox: true, margin: 0 });
  s.addText("AI Systems Architecture Review", { x: 0.6, y: 2.2, w: 8, h: 0.5, fontFace: BF, fontSize: 22, color: ICE, isTextBox: true, margin: 0 });
  s.addText("Verifiable, tenant-isolated LLM inference controls for regulated AI — reproducibility receipts, and a measured cross-tenant cache-leak fix", { x: 0.6, y: 2.78, w: 8.7, h: 0.7, fontFace: BF, fontSize: 13, italic: true, color: ICE, isTextBox: true, margin: 0 });
  s.addText("Release/ship date · 12 September 2026 · Roshan Rana, AI Systems Architect", { x: 0.6, y: 4.6, w: 8.8, h: 0.3, fontFace: BF, fontSize: 10, color: MUTED, isTextBox: true, margin: 0 });
  s.addShape(pres.shapes.OVAL, { x: 8.2, y: 1.2, w: 1.1, h: 1.1, fill: { color: MINT }, line: { color: MINT } });
  s.addText("P", { x: 8.2, y: 1.2, w: 1.1, h: 1.1, fontFace: HF, fontSize: 40, bold: true, color: NAVY, align: "center", valign: "middle", isTextBox: true, margin: 0 });
}

// ---------- 2 Executive summary
{
  const s = base("Executive summary", "Overview");
  const cols = [
    ["What it is", ["Two working controls for a bank's shared LLM inference platform: ATTEST proves a model's output is reproducible enough for a validator (SR 11-7); BARRIER closes a routing-layer channel that leaks one tenant's prompts to another.", "Both ship against real vLLM, SGLang and llm-d — not a mock of them."]],
    ["What it proves", ["Batched inference at temperature 0 is not reproducible: 34 of 128 identical requests returned distinct logprob vectors. Determinism costs 18.0% of throughput isolated from caching (SGLang), 22.7% confounded with it (vLLM).", "The routing-index leak is real (AUC 1.0000, p=9.999e-05) and the tenant-salt fix closes it (AUC 0.5000, at chance) — same schedule, same pre-registered rule, measured in public CI on every push for £0."]],
    ["Why it is enterprise-ready", ["A gated lifecycle (phases 0–7), 12 ADRs and a 27-entry findings log — four of them guards that contained the defect they were written to catch, kept rather than hidden.", "332 Python + Go tests; the statistics are implemented and unit-tested in-house so a reviewer can read the decision rule rather than trust a library call."]],
  ];
  cols.forEach((c, i) => {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.3, 2.9, 3.25);
    s.addText(c[0], { x: x + 0.15, y: 1.4, w: 2.6, h: 0.35, fontFace: HF, fontSize: 15, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    bullets(s, c[1], x + 0.15, 1.85, 2.6, 2.6, 10.5);
  });
  s.addText("Ask of the audience: agree the pilot scope for the two open measurements — a client-observable timing oracle on real vLLM (FR-B-09) and a signed receipt against a live engine — and the GPU budget for the next session.", { x: 0.5, y: 4.7, w: 9, h: 0.45, fontFace: BF, fontSize: 10.5, italic: true, color: INK, isTextBox: true, margin: 0 });
}

// ---------- 3 Problem and users
{
  const s = base("The problem and the users", "Context");
  box(s, 0.5, 1.3, 4.3, 1.75, "The model-risk problem", "SR 11-7 and its analogues assume a model's output can be reproduced. On a default vLLM deployment the honest answer is that nobody can: batched inference is not deterministic even at temperature 0, because GPU kernels pick different reduction orders depending on what else is in the batch.", { bs: 10 });
  box(s, 5.2, 1.3, 4.3, 1.75, "The information-barrier problem", "llm-d's cache-aware router makes a shared platform fast by routing matching prompt prefixes to the pod that already holds them. In a bank the prefixes are the sensitive part — by default, two tenants on one model share one routing namespace.", { bs: 10 });
  table(s, [
    ["Actor", "Needs", "Frequency"],
    ["Model validator / auditor", "Demonstrable reproducibility for a specific output, model identity anchored outside the platform team's control", "On review"],
    ["Platform / SRE team", "A mitigation that ships as a plugin, not a fork, and a diff that states exactly what changed", "Deploy / operate"],
    ["Compliance / InfoSec", "Evidence the routing layer cannot leak across an information barrier, and an honest account of what was and was not measured", "Ongoing"],
    ["Tenants (Research vs M&A)", "The same shared platform, and a guarantee neither can observe what the other is asking", "Every request"],
  ], 0.5, 3.25, 9.0, [2.4, 5.1, 1.5], 8.7);
}

// ---------- 4 Solution at a glance
{
  const s = base("Solution at a glance", "Approach");
  const steps = [
    ["1", "Measure", "Drive a matrix of prompts, batch shapes and seeds through a real engine; record raw logprobs to an append-only, resumable ledger."],
    ["2", "Quantify + attest", "Bootstrap CI on the cost of determinism; decompose it across two engines; sign a receipt anchored to a Hugging Face commit SHA and weight digest."],
    ["3", "Probe", "Stand up a two-tenant llm-d cluster in kind; probe the prefix-cache router with a pre-registered AUC/bootstrap/permutation rule fixed before any attack code existed."],
    ["4", "Close it", "An out-of-tree EPP plugin binds the cache salt to authenticated identity; Envoy strips and re-injects it before ext_proc; both profiles run in CI on every push."],
  ];
  steps.forEach((st, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.35, 2.15, 2.15, CARD_D, CARD_D);
    s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.5, w: 0.4, h: 0.4, fill: { color: MINT }, line: { color: MINT } });
    s.addText(st[0], { x: x + 0.15, y: 1.5, w: 0.4, h: 0.4, fontFace: BF, fontSize: 14, bold: true, color: NAVY, align: "center", valign: "middle", isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.65, y: 1.52, w: 1.4, h: 0.36, fontFace: BF, fontSize: 12.5, bold: true, color: WHITE, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(st[2], { x: x + 0.15, y: 2.0, w: 1.85, h: 1.4, fontFace: BF, fontSize: 8.5, color: ICE, isTextBox: true, margin: 0, valign: "top" });
    if (i < 3) arrow(s, x + 2.15, 2.4, x + 2.3, 2.4, MINT, 2);
  });
  box(s, 0.5, 3.75, 4.4, 1.3, "Surfaces", "attest CLI (verify exit codes 0/2/3/4/5/6) · barrier attack scripts · common/stats library · GitHub Actions. No service, no dashboard — every published number is a file under git.", { bs: 9.5 });
  box(s, 5.1, 3.75, 4.4, 1.3, "Two workstreams, one shared library (D-04)", "ATTEST needs a rented GPU for about $2.00 total. BARRIER's kind cluster runs in public CI for £0. Neither blocks the other's ship; both share common/stats only.", { bs: 9.5 });
}

// ---------- 5 System context (C4 L1)
{
  const s = base("System context", "Architecture · C4 level 1");
  const actors = [["Reviewer", "clone + run, no GPU"], ["Roshan (operator)", "GPU session + cluster"], ["Model validator", "verifies a receipt alone"]];
  actors.forEach((a, i) => { box(s, 0.5, 1.3 + i * 1.1, 1.7, 0.95, a[0], a[1], { bs: 8.5 }); arrow(s, 2.2, 1.78 + i * 1.1, 2.75, 2.85, MUTED, 1); });
  card(s, 2.8, 1.3, 3.4, 3.4, "EEF6F4", MINT);
  s.addText("PROVENANCE", { x: 2.95, y: 1.38, w: 3, h: 0.3, fontFace: HF, fontSize: 13, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  box(s, 2.95, 1.75, 3.1, 0.65, "Surfaces", "attest CLI · barrier attack scripts", { bs: 8.5 });
  box(s, 2.95, 2.5, 3.1, 1.05, "ATTEST + BARRIER", "harness · receipt · analysis / attack · epp · deploy — common/stats shared by both", { bs: 8.5 });
  box(s, 2.95, 3.65, 3.1, 0.9, "bench/results/", "immutable raw evidence; single writer per run-id", { bs: 8.5 });
  box(s, 6.9, 1.3, 2.6, 0.75, "Hugging Face Hub", "model identity: commit SHA + LFS weight digest", { bs: 8 });
  box(s, 6.9, 2.2, 2.6, 0.75, "vLLM / SGLang engine", "rented GPU, SM ≥ 8.0, released same day", { bs: 8 });
  box(s, 6.9, 3.1, 2.6, 0.75, "kind cluster", "llm-d Router + simulator pods, two tenants", { bs: 8 });
  box(s, 6.9, 4.0, 2.6, 0.7, "GitHub Actions", "make check · BARRIER cluster workflow", { bs: 8 });
  arrow(s, 6.2, 3.0, 6.9, 1.67, MUTED, 1); arrow(s, 6.2, 3.1, 6.9, 2.57, MUTED, 1); arrow(s, 6.2, 3.2, 6.9, 3.47, MUTED, 1); arrow(s, 6.2, 3.3, 6.9, 4.35, MUTED, 1);
  s.addText("Build/measure-time only: the GPU engine is rented by the hour and released the same day; the kind cluster stands up fresh in CI on every push. Nothing here is an always-on service.", { x: 0.5, y: 4.85, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 6 Component architecture (C4 L2)
{
  const s = base("Component architecture", "Architecture · C4 level 2 · HLD §4, C1–C8");
  const groups = [
    { t: "ATTEST — harness (C1)", x: 0.5, items: [["matrix.py", "prompts × batch × seed"], ["ledger.py", "cells.jsonl, resumable"], ["engine / vllm / sglang", "engine lifecycle"], ["run.py", "cell → JSONL + receipt"]] },
    { t: "ATTEST — receipt/analysis (C2,C3)", x: 2.85, items: [["schema / canonical", "in-toto + JCS"], ["sign.py / cli.py", "ed25519, exit codes"], ["provenance.py", "HF commit + LFS digest"], ["cost / divergence", "CIs, no engine access"]] },
    { t: "BARRIER (C4,C5,C6)", x: 5.2, items: [["spike_s02 / demo_frb03", "the oracle + FR-B-03 probe"], ["ground_truth.py", "prefix-index truth"], ["plugin.go / salt.go", "tenant-salt EPP plugin"], ["values-*.yaml", "default vs hardened"]] },
    { t: "common + evidence (C7,C8)", x: 7.55, items: [["auc / permutation", "rank AUC, permutation test"], ["decision.py", "the pre-registered verdict"], ["calibration / noise", "200-dataset CI check"], ["bench/results/", "immutable, single-writer"]] },
  ];
  groups.forEach((g) => {
    card(s, g.x, 1.3, 2.15, 3.55);
    s.addText(g.t, { x: g.x + 0.1, y: 1.36, w: 2, h: 0.3, fontFace: BF, fontSize: 9.5, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    g.items.forEach((it, i) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: g.x + 0.1, y: 1.72 + i * 0.62, w: 1.95, h: 0.54, fill: { color: WHITE }, line: { color: LINE, width: 0.75 }, rectRadius: 0.05 });
      s.addText(it[0], { x: g.x + 0.18, y: 1.75 + i * 0.62, w: 1.8, h: 0.24, fontFace: "Courier New", fontSize: 8, bold: true, color: NAVY, isTextBox: true, margin: 0 });
      s.addText(it[1], { x: g.x + 0.18, y: 1.97 + i * 0.62, w: 1.8, h: 0.26, fontFace: BF, fontSize: 7.7, color: INK, isTextBox: true, margin: 0 });
    });
  });
  arrow(s, 2.65, 3.1, 2.85, 3.1, MINT, 2); arrow(s, 5.0, 3.1, 5.2, 3.1, MINT, 2); arrow(s, 7.35, 3.1, 7.55, 3.1, MINT, 2);
  s.addText("Responsibilities do not overlap (HLD §4): C3 never touches an engine, C1 never computes a statistic, C4 never decides whether a result passes — that is C7's pre-registered test.", { x: 0.5, y: 4.9, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 7 The FR-B-03 measurement pipeline
{
  const s = base("The critical flow: measuring the cross-tenant leak", "Architecture · critical flow · FR-B-03");
  const stages = [
    ["Plant", "tenant B submits a fresh nonce prefix nobody has sent before"],
    ["Probe +", "tenant A submits the identical text — the positive class"],
    ["Probe −", "tenant A submits a different fresh nonce — the negative class, same tenant, same key, same length"],
    ["Read", "match ratio read from the EPP's own prefix_indexer_hit_ratio histogram, attributed to exactly one request"],
    ["Guard", "refuse the trial if the counter moved by anything other than one — another client or a retry would corrupt it"],
    ["Score", "common/stats/decision.py: AUC ≥ 0.75, CI excludes 0.5, p < 0.01 for the attack; CI contains 0.5 for the mitigation"],
    ["Repeat", "both profiles, same schedule, 40 trials per profile — in GitHub Actions, on every push"],
    ["Verdict", "attack_succeeds / at_chance / neither — the middle case is a real state, not a bug"],
  ];
  stages.forEach((st, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = 0.5 + col * 2.3, y = 1.4 + row * 1.7;
    card(s, x, y, 2.15, 1.35, row === 0 ? CARD : "EEF6F4", row === 0 ? LINE : MINT);
    s.addText(`${i + 1}. ${st[0]}`, { x: x + 0.1, y: y + 0.08, w: 1.95, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.1, y: y + 0.4, w: 1.95, h: 0.9, fontFace: BF, fontSize: 8, color: INK, isTextBox: true, margin: 0, valign: "top" });
    if (col < 3) arrow(s, x + 2.15, y + 0.67, x + 2.3, y + 0.67, MUTED, 1.25);
  });
  arrow(s, 9.0, 2.75, 9.0, 3.1, MUTED, 1.25);
  s.addText("The rule was fixed in LLD §7 before any attack code existed. It has already returned 'neither' once (S-02, ADR-011) and both extremes once (FR-B-03, ADR-012) — never adjusted to fit.", { x: 0.5, y: 4.85, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 8 Core mechanism
{
  const s = base("A verdict fixed before the evidence", "Design · the pre-registered decision rule");
  card(s, 0.5, 1.3, 4.6, 3.55, CARD_D, CARD_D);
  s.addText("What the rule requires (common/stats/decision.py)", { x: 0.65, y: 1.38, w: 4.3, h: 0.3, fontFace: BF, fontSize: 10.5, bold: true, color: MINT, isTextBox: true, margin: 0 });
  s.addText([
    "attack_succeeds:", "  auc >= 0.75", "  ci_lower_bound > 0.5", "  p < 0.01", "at_chance:", "  ci contains 0.5", "otherwise:", "  inconclusive   # neither claim",
  ].join("\n"), { x: 0.65, y: 1.72, w: 4.3, h: 1.7, fontFace: "Courier New", fontSize: 10, color: WHITE, isTextBox: true, margin: 0, valign: "top" });
  s.addText("Why it holds up", { x: 0.65, y: 3.45, w: 4.3, h: 0.3, fontFace: BF, fontSize: 10.5, bold: true, color: MINT, isTextBox: true, margin: 0 });
  bullets(s, ["one function scores both the attack and the mitigation — nothing to let them silently drift apart", "implemented in common/stats/ rather than imported: a reviewer can read the whole rule in about forty lines", "bootstrap calibration-tested over 200 null datasets: nominal 95% should cover truth ~95% of the time (91.0% observed)"], 0.65, 3.78, 4.3, 1.0, 8.7, ICE);
  const badges = [["attack_succeeds", "default profile, run #15: AUC 1.0000, p=9.999e-05", MINT], ["at_chance", "hardened profile, run #15: AUC 0.5000, same schedule", GOLD], ["inconclusive", "S-02 simulator, run #12: AUC 0.5581 [0.5026,0.6138]", RED]];
  badges.forEach((b, i) => {
    const y = 1.3 + i * 0.75;
    card(s, 5.4, y, 4.1, 0.68);
    s.addText(b[0], { x: 5.55, y: y + 0.05, w: 1.9, h: 0.58, fontFace: BF, fontSize: 11.5, bold: true, color: b[2], isTextBox: true, margin: 0, valign: "middle" });
    s.addText(b[1], { x: 7.35, y: y + 0.05, w: 2.05, h: 0.58, fontFace: BF, fontSize: 8, color: INK, isTextBox: true, margin: 0, valign: "middle" });
  });
  box(s, 5.4, 3.6, 4.1, 1.28, "Why this mattered twice", "S-02 returned 'ORACLE VIABLE' on a plain millisecond counter — twice — because a five-name ignore-list only excludes noise you already named. The fix was a property test, not a longer list. Two more guards (F-25, F-26) failed the same way before the ground-truth check became tested code.", { bs: 8.3 });
}

// ---------- 9 Data architecture
{
  const s = base("Data architecture: no database, by design", "Architecture · data · ADR-001");
  box(s, 0.5, 1.3, 4.3, 1.6, "Raw evidence (C1, C4)", "bench/results/<workstream>-<UTC timestamp>-<git SHA>/ — JSONL run output + manifest.json (command, SHA, env, timestamps). Single writer per run-id; immutable once the manifest finalises. Analysis reads, never mutates.", { bs: 9 });
  box(s, 0.5, 3.05, 4.3, 1.75, "Receipts (C2)", "in-toto-style JSON + detached ed25519 signature, JCS-canonicalised so two serialisations produce identical bytes. Model identity anchors to the Hugging Face Hub commit SHA and LFS weight digest — a root the platform team does not control.", { bs: 9 });
  card(s, 5.05, 1.9, 2.35, 1.85, "EEF6F4", MINT);
  s.addText("Three kinds of file, all under git", { x: 5.15, y: 1.98, w: 2.15, h: 0.5, fontFace: BF, fontSize: 10, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  s.addText("raw output\nreceipts\nmetrics/headline.json", { x: 5.15, y: 2.45, w: 2.15, h: 1.2, fontFace: "Courier New", fontSize: 9.5, color: INK, isTextBox: true, margin: 0 });
  arrow(s, 4.8, 2.8, 5.05, 2.8, MINT, 2);
  box(s, 7.55, 1.3, 1.95, 3.55, "Figures, generated not drawn", "docs/figures/*.svg regenerated by scripts/make_figures.py from bench/results/measurements.json. tests/test_published_numbers.py fails the build if README or the ship report drifts from it.", { bs: 8.3 });
  s.addText("A database would put a published number behind something that can drift (ADR-001) — the opposite of what a repository whose entire subject is verifiable claims can afford.", { x: 0.5, y: 4.95, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 10 Engines, plugin, and the trust-boundary ordering
{
  const s = base("Two engines, one plugin, and where the boundary sits", "Architecture · integration");
  box(s, 0.5, 1.3, 4.3, 1.65, "Two engines, one seam (C1)", "attest/harness/engine.py defines one client interface; vllm.py and sglang.py implement its lifecycle. SGLang entered as a control arm (ADR-009) to decompose vLLM's confounded cost number — methodology, not coverage.", { bs: 9 });
  box(s, 5.2, 1.3, 4.3, 1.65, "One plugin, no fork (ADR-002)", "llm-d-router exports Register() and a package-level Registry, so barrier/epp/cmd/epp blank-imports the tenant-salt plugin and runs upstream's runner unmodified. Upgrades are a go.mod bump plus a compile check.", { bs: 9 });
  box(s, 0.5, 3.1, 4.3, 1.7, "Ordering is the whole trust boundary (F-27)", "Envoy applies route-level header mutations in the router filter, which runs AFTER ext_proc — a naive strip-and-inject never reaches the EPP. The fix places envoy.filters.http.header_mutation before ext_proc, and overwrites rather than remove-then-add, because Envoy applies removes after adds.", { bs: 8.7 });
  box(s, 5.2, 3.1, 4.3, 1.7, "The only 'live' surface is CI", "The two-tenant kind topology (llm-d Router + simulator pods) stands up fresh in GitHub Actions on every push to barrier/**, both profiles, £0 — the BARRIER cluster workflow, active and running since 2026-09-07.", { bs: 9 });
}

// ---------- 11 Design choices
{
  const s = base("Design choices and why", "Design decisions");
  table(s, [
    ["Decision", "Alternatives considered", "Why this one"],
    ["Monorepo of CLIs, no services (ADR-001)", "Results service + dashboard; one unified CLI", "Files under git are the simplest traceability story; a database puts published numbers behind something that can drift"],
    ["Out-of-tree Go module, no fork (ADR-002)", "Fork llm-d-router; configuration-only mitigation", "Register/Registry are exported — a droppable plugin is stronger than a fork reviewers discount"],
    ["Own the AUC/bootstrap/permutation test (ADR-003)", "scikit-learn roc_auc_score; statsmodels", "A reviewer assessing a security claim should read the forty-line test, not trust a library call"],
    ["Helm, two values files as the deliverable (ADR-004)", "Kustomize overlays; raw YAML per config", "The diff between values-default.yaml and values-hardened.yaml IS the argument"],
    ["ed25519 + in-toto predicate, sigstore deferred (ADR-005)", "Sigstore keyless via cosign", "Keyless signing needs network + OIDC at verify time, breaking the no-accounts path (D-13)"],
    ["Strip identity at the proxy, fail closed (ADR-006)", "Add the header to llm-d's own InputControlHeaders; trust it as received", "Upstream's set is a hardcoded package var; the proxy boundary needs no upstream change"],
    ["SGLang as ATTEST's control arm (ADR-009)", "Publish the confounded vLLM number with a caveat; drop the claim", "SGLang runs deterministic with its cache on, supplying the missing 2×2 cell"],
  ], 0.5, 1.3, 9.0, [2.7, 2.9, 3.4], 8.3);
}

// ---------- 12 Major features
{
  const s = base("Major features", "Product");
  const feats = [
    ["Signed attestation receipts", "in-toto statement, JCS-canonicalised, ed25519-signed; model identity anchored to a Hugging Face commit SHA and LFS weight digest, not a local hash"],
    ["Resumable measurement harness", "matrix.py × ledger.py: a run that dies at cell 340 of 600 resumes at 341; raw output committed before analysis reads it"],
    ["Cost-of-determinism decomposition", "a 2×2 across vLLM and SGLang isolates determinism's cost (18.0%) from the prefix cache's (a 7.9% penalty on this workload)"],
    ["Tenant-salt EPP plugin", "out-of-tree, registered via llm-d's exported Registry; HMAC-derives a salt from authenticated identity, propagates it to vLLM's own cache too"],
    ["Two-tenant kind topology in CI", "both deployment profiles stood up fresh on every push to barrier/**; the FR-B-03 measurement runs against them for £0"],
    ["Pre-registered statistics library", "AUC, bootstrap CI, permutation test, calibration-tested over 200 null datasets; the decision rule is frozen before any attack code"],
    ["attest verify CLI", "a full exit-code contract: 0 valid, 2 signature invalid, 3 digest mismatch, 4 malformed, 5 Hub unreachable, 6 identity divergent"],
    ["barrier-diff", "the entire mitigation presented as a three-change YAML diff between values-default.yaml and values-hardened.yaml"],
    ["STATE.md findings log", "27 findings (F-01…F-27) — the project's own record of what it got wrong and how each was caught"],
  ];
  feats.forEach((f, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    box(s, 0.5 + col * 3.05, 1.3 + row * 1.2, 2.9, 1.05, f[0], f[1], { bs: 8 });
  });
}

// ---------- 13 Figure: divergence
{
  const s = base("Batched inference is not reproducible", "Measured · docs/RESULTS.md §1");
  imgFit(s, ASSETS + "20-divergence.png", 0.6, 1.3, 6.1, 3.15, 2160, 960);
  box(s, 6.95, 1.3, 2.55, 1.95, "What this shows", "128 identical requests, temperature 0, seed fixed. VLLM_BATCH_INVARIANT=1 cuts 34 distinct outputs to 5 — a large mitigation, not a guarantee. SGLang's deterministic mode reached 1 of 128.", { bs: 8.7 });
  box(s, 6.95, 3.35, 2.55, 1.5, "What it does not establish", "The two engines ran under their own defaults and schedulers — read as two measurements, not a controlled comparison (README).", { bs: 8.7 });
}

// ---------- 14 Figure: cost decomposition
{
  const s = base("The cost of determinism, decomposed", "Measured · docs/RESULTS.md §2 · ADR-009");
  imgFit(s, ASSETS + "21-cost-decomposition.png", 0.6, 1.3, 6.4, 3.55, 2160, 1116);
  box(s, 7.2, 1.3, 2.3, 1.95, "Why a second engine", "vLLM cannot run batch-invariant with prefix caching on, so its 22.7% number is determinism plus the loss of the cache. SGLang runs deterministic with its cache on, supplying the missing 2×2 cell.", { bs: 8.3 });
  box(s, 7.2, 3.35, 2.3, 1.5, "The counter-intuitive part", "The confounded figure (0.848×) understates the isolated cost (0.820×) here — the two effects partly cancel on this short-prompt workload.", { bs: 8.3 });
}

// ---------- 15 Figure: FR-B-03 verdict
{
  const s = base("The cross-tenant leak, and the mitigation closing it", "Measured · docs/RESULTS.md §3 · ADR-012, CI run #15");
  imgFit(s, ASSETS + "22-frb03-verdict.png", 0.6, 1.3, 6.4, 3.55, 2160, 1002);
  box(s, 7.2, 1.3, 2.3, 1.95, "Same schedule, same rule", "40 trials per profile, n=80. default clears the pre-registered bar (AUC 1.0000, p=9.999e-05); hardened lands exactly at chance (AUC 0.5000) — the same instrument, the same threshold.", { bs: 8.3 });
  box(s, 7.2, 3.35, 2.3, 1.5, "Scope, stated plainly", "A confirmation oracle: the probe sends the victim's prompt verbatim, so 1.0 is by construction. It shows a guessed prefix confirmed, not unknown content recovered.", { bs: 8 });
}

// ---------- 16 Figure: S-02 power
{
  const s = base("What a pre-registered rule is actually for", "Measured · docs/RESULTS.md §4 · ADR-011, CI run #12");
  imgFit(s, ASSETS + "23-s02-power.png", 0.6, 1.3, 6.4, 3.55, 2160, 1116);
  box(s, 7.2, 1.3, 2.3, 2.1, "Two wrong-shaped answers first", "Two runs at n=62 put the AUC point estimate above chance with an interval straddling it — not evidence of no effect, just an underpowered sample.", { bs: 8.3 });
  box(s, 7.2, 3.5, 2.3, 1.35, "n=402 fixed in advance", "AUC 0.5581 [0.5026, 0.6138], p=0.0425 — clears none of the three thresholds. 'No oracle', stated precisely, not 'no effect'.", { bs: 8 });
}

// ---------- 17 Screenshots: confirming the numbers
{
  const s = base("Confirming the numbers, and the receipt pipeline", "Screenshots · this review's own runs");
  imgFit(s, ASSETS + "10-headline-run.png", 0.5, 1.3, 4.3, 3.5, 1200, 566);
  imgFit(s, ASSETS + "11-receipt-verify.png", 5.1, 1.3, 4.3, 3.5, 1200, 425);
  caption(s, "Left: make headline / make card / make card-check, then the full pytest run (331 passed, 1 Windows-only failure, 111s). Right: make attest-demo — signs a receipt, then tampers with it three ways and requires the verifier to catch every one ('valid=0, tampered=3').", 0.5, 4.95, 9);
}

// ---------- 18 Screenshots: the mitigation and its proof
{
  const s = base("The mitigation, and proof it compiles", "Screenshots · make barrier-diff · barrier/epp");
  imgFit(s, ASSETS + "12-barrier-diff.png", 0.5, 1.3, 4.3, 3.5, 1200, 539);
  imgFit(s, ASSETS + "13-epp-go-tests.png", 5.1, 1.3, 4.3, 3.5, 1200, 717);
  caption(s, "Left: the entire mitigation as a three-change YAML diff — plugin declaration, salt propagated to vLLM's own cache, proxy strip-and-inject. Right: go build/vet/test against the real llm-d-router v0.10.0 graph — 19 test functions (26 with subtests), all passing.", 0.5, 4.95, 9);
}

// ---------- 17 Security and compliance
{
  const s = base("Security and compliance controls", "Enterprise readiness · controls");
  table(s, [
    ["Boundary", "Threat", "Control in the code", "Evidence"],
    ["Proxy (trust boundary)", "attacker-supplied identity header", "strip x-llmd-tenant, inject vouched identity via OVERWRITE_IF_EXISTS_OR_ADD, before ext_proc", "run #13: 401 unauthenticated; F-27 fix"],
    ["EPP prefix index (approximate)", "omission / forgery / negligence of client-supplied cache_salt", "salt is HMAC-derived from vouched identity; failClosed rejects absent/malformed identity", "ADR-012 run #15: default AUC 1.0000, hardened 0.5000"],
    ["Engine cache (precise path)", "salt closes routing index but leaves vLLM's own KV cache shared", "plugin rewrites the outbound cache_salt so the engine partitions identically (obligation 3)", "Go test: all 7 body variants covered"],
    ["Salt secret", "a compromised secret derives every tenant's salt", "min 32 bytes, mounted from a Secret, never logged, never in values files", "threat-model.md §8"],
    ["Receipt verifier", "a claim the platform team could fabricate", "model identity anchors to the HF Hub commit SHA + LFS digest, a root we do not control", "attest verify --online, exit codes 5/6"],
  ], 0.5, 1.3, 9.0, [1.5, 2.3, 3.4, 1.8], 8);
  s.addText("Residual risks are written down, not hidden: no authentication on the demo cluster beyond the proxy; a compromised salt secret restores every forgery; the client-observable oracle on real vLLM (FR-B-09) is unmeasured.", { x: 0.5, y: 4.7, w: 9, h: 0.4, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 18 Enterprise readiness: process
{
  const s = base("How it was built: a gated lifecycle", "Enterprise readiness · process");
  const gates = ["P0 brief", "P1 HLD", "P2 LLD", "P3 plan", "P4 build", "P5 measure", "P6 amend", "P7 shipped"];
  gates.forEach((g, i) => {
    const x = 0.5 + i * 1.13;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.35, w: 1.05, h: 0.62, fill: { color: i < 7 ? CARD_D : "1E5C57" }, line: { color: i < 7 ? CARD_D : "1E5C57" }, rectRadius: 0.05 });
    s.addText(g, { x: x + 0.04, y: 1.37, w: 0.97, h: 0.58, fontFace: BF, fontSize: 8, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  });
  const stats = [["12", "ADRs, each with options considered and consequences accepted — several overturning the original brief"], ["27", "findings logged in STATE.md (F-01…F-27); four are guards that contained the defect they were written to catch"], ["50", "tasks across 7 milestones in the execution plan; 6 detailed packs committed for the earliest waves"], ["$2.00", "total rented GPU spend across six pods for every ATTEST number in this repository"]];
  stats.forEach((st, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 2.2, 2.15, 1.25);
    s.addText(st[0], { x: x + 0.12, y: 2.25, w: 1.9, h: 0.5, fontFace: HF, fontSize: 26, bold: true, color: GOLD, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.12, y: 2.75, w: 1.9, h: 0.65, fontFace: BF, fontSize: 8, color: INK, isTextBox: true, margin: 0, valign: "top" });
  });
  box(s, 0.5, 3.65, 4.4, 1.25, "Pre-registered, not post-hoc", "BARRIER's success criteria (AUC ≥ 0.75, CI excludes 0.5, p < 0.01) were committed before any attack code existed, and the git history shows that ordering.", { bs: 9 });
  box(s, 5.1, 3.65, 4.4, 1.25, "One command validates everything", "ruff · ruff format · mypy strict · pytest (332 tests) · Go build/vet/test — make check. CI is meant to mirror it exactly; a step that passes locally and fails there is treated as the bug.", { bs: 9 });
}

// ---------- 19 Quality metrics (native chart)
{
  const s = base("Quality metrics from this review's own runs", "Enterprise readiness · measurement");
  s.addChart(pres.charts.BAR, [{ name: "Value", labels: ["Bootstrap CI coverage", "Python test pass rate", "Go test pass rate", "Claims verifiable offline"], values: [0.910, 0.997, 1.000, 0.364] }], {
    x: 0.5, y: 1.3, w: 5.2, h: 3.5, barDir: "bar", chartColors: [MINT], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelFontSize: 9, dataLabelColor: INK,
    catAxisLabelColor: INK, catAxisLabelFontSize: 9, valAxisLabelColor: MUTED, valAxisLabelFontSize: 8, valAxisMinVal: 0, valAxisMaxVal: 1.1, valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Ratios (1.0 = clean)", titleFontSize: 10, titleColor: NAVY,
  });
  table(s, [
    ["KPI", "Value", "Source"],
    ["Python tests", "331 passed, 1 failed (Windows-only) of 332", "pytest, this run"],
    ["Go tests (barrier/epp)", "19 funcs / 26 with subtests, all pass", "go test, this run"],
    ["ADRs / findings logged", "12 / 27 (4 self-catching guards)", "decisions.md"],
    ["Cross-tenant leak (default)", "AUC 1.0000, p=9.999e-05, n=80", "ADR-012, run #15"],
    ["Mitigation (hardened)", "AUC 0.5000, at chance, n=80", "ADR-012, run #15"],
    ["Determinism cost, isolated", "18.0% (SGLang, D/B = 0.820×)", "ADR-009, H100"],
    ["Determinism cost, confounded", "22.7%, 95% CI [0.741, 0.808] (vLLM)", "bench/results"],
  ], 5.9, 1.3, 3.6, [1.45, 1.35, 0.8], 7.3);
  s.addText("The one Python failure asserts a 0600 file-mode; Windows filesystems do not enforce that bit the way POSIX does. Confirmed pre-existing and platform-specific during this review — not a defect in the path CI actually runs (ubuntu-latest).", { x: 0.5, y: 4.9, w: 9, h: 0.35, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 20 Quirks and limitations
{
  const s = base("Quirks and known limitations (stated, not hidden)", "Honesty");
  const q = [
    ["A confirmation oracle, not an extraction one", "FR-B-03's probe sends the victim's prompt verbatim, so AUC 1.0 is by construction. It shows a guessed prefix gets confirmed; nothing about recovering unknown content (ADR-012)."],
    ["No client-observable oracle — on the simulator", "S-02: latency AUC 0.5581 [0.5026, 0.6138], p=0.0425 — clears none of the three thresholds. Real vLLM does vary TTFT with cache state; that question is FR-B-09, open."],
    ["Two engines, not a controlled comparison", "vLLM and SGLang ran under their own defaults and schedulers. The gap between 34 and 3 (determinism off) is larger than the determinism question alone explains."],
    ["No signed receipt against a real engine", "attest-demo exercises the full pipeline, tamper detection included, against a stub. The GPU runs measured divergence and cost but emitted no receipts."],
    ["Four guards contained the bug they targeted", "F-14, F-23, F-25, F-26: a comparison-arm guard that failed open, a millisecond counter mistaken for a discriminator (twice), a ground-truth gate that proved a plugin ran, not that it matched."],
    ["CI is disabled; only the cluster workflow runs", "The CI workflow is manually disabled on GitHub; BARRIER cluster is the only active workflow, standing up both profiles on every push (confirmed via gh workflow list --all)."],
    ["One pytest failure, Windows-only", "test_private_key_is_written_unreadable_to_others asserts a 0600 file mode Windows does not express the same way. 331 of 332 pass on this host."],
    ["Pre-existing lint/type debt in metrics/render.py", "ruff found 2 E501 lines and mypy found missing dict[...] type args during this review's confirmation run — present before this task, left unfixed as out of scope."],
  ];
  q.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    box(s, 0.5 + col * 4.6, 1.3 + row * 0.9, 4.45, 0.82, it[0], it[1], { bs: 7.6, ts: 9.5 });
  });
}

// ---------- 21 Cost and performance
{
  const s = base("Cost, performance and operability", "Enterprise readiness · operations");
  const cards = [["$2.00", "total rented GPU spend (H100 + A40, six pods) for every ATTEST number in the repository"], ["£0", "BARRIER's two-tenant kind cluster, both profiles, stood up fresh in GitHub Actions on every push"], ["111s", "the 332-test Python suite on this host (0:01:51); Go build+vet+test completes in well under a second"], ["8", "components, no services (HLD §4) — every artifact is a file under git, traced to a command and a SHA"]];
  cards.forEach((c, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.3, 2.15, 1.35);
    s.addText(c[0], { x: x + 0.12, y: 1.35, w: 1.9, h: 0.5, fontFace: HF, fontSize: 24, bold: true, color: GOLD, isTextBox: true, margin: 0 });
    s.addText(c[1], { x: x + 0.12, y: 1.87, w: 1.9, h: 0.75, fontFace: BF, fontSize: 8, color: INK, isTextBox: true, margin: 0, valign: "top" });
  });
  box(s, 0.5, 2.85, 4.4, 2.0, "Operability", "• STATE.md is the single source of truth for where the project stands — no repo-wide crawl needed to resume\n• bench/results/ keeps the runs that were wrong alongside the ones that were right, each with the reason attached\n• make check is the one gate agents, humans and CI all run\n• make headline / make card regenerate the offline metrics card and fail the build on drift", { bs: 8.7 });
  box(s, 5.1, 2.85, 4.4, 2.0, "What is not yet instrumented", "• No alerting, no dashboard, no production deployment target — this is a measurement rig and a shipped mitigation, not a running service\n• The GPU session is staged with a human decision point precisely because it is rented hardware, not standing infrastructure\n• CI currently runs only the BARRIER cluster workflow (see Quirks)", { bs: 8.7 });
}

// ---------- 22 Roadmap
{
  const s = base("Roadmap — none of it load-bearing", "Next steps");
  const phases = [["Next", "Real timing oracle", ["FR-B-09 on real vLLM, where TTFT does vary with cache state", "The simulator could not answer it (ADR-011) — this is the last open client-observable question"]], ["Then", "Continuous prefixes", ["FR-B-03's separation is binary today (identical or disjoint)", "A shared system prompt with differing tails makes the match ratio continuous and the interval non-degenerate"]], ["Then", "Receipt on a live engine", ["Sign a receipt against real vLLM/SGLang output, not the stub", "Extend the tamper-detection test to that path"]], ["Later", "Open statistical questions", ["Confidence intervals on the SGLang 2×2; SGLang's Triton backend", "Why vLLM's batch-invariant mode leaves 5 residual vectors of 128 where SGLang leaves 1"]]];
  phases.forEach((p, i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.3, 2.15, 3.5, i === 0 ? "EEF6F4" : CARD, i === 0 ? MINT : LINE);
    s.addText(p[0], { x: x + 0.12, y: 1.36, w: 1.9, h: 0.28, fontFace: BF, fontSize: 9, bold: true, color: MINT, charSpacing: 1, isTextBox: true, margin: 0 });
    s.addText(p[1], { x: x + 0.12, y: 1.62, w: 1.9, h: 0.6, fontFace: HF, fontSize: 12.5, bold: true, color: NAVY, isTextBox: true, margin: 0 });
    bullets(s, p[2], x + 0.12, 2.25, 1.9, 2.5, 8.3);
  });
  s.addText("STATE.md lists all of this explicitly as 'none of it load-bearing' — both workstreams already have their headline result measured.", { x: 0.5, y: 4.95, w: 9, h: 0.3, fontFace: BF, fontSize: 9, italic: true, color: MUTED, isTextBox: true, margin: 0 });
}

// ---------- 23 Appendix: decision log
{
  const s = base("Appendix A — Decision log (abridged)", "Appendix");
  table(s, [
    ["ID", "Decision", "Consequence"],
    ["ADR-001", "Monorepo of CLIs, no services", "No runtime to maintain; a dashboard, if ever built, is a mirror, never a source of truth"],
    ["ADR-002", "Out-of-tree Go module, no fork", "We track the runner API across releases; upgrades are a go.mod bump plus a compile check"],
    ["ADR-003", "Own the AUC/bootstrap/permutation test", "Both the attack and mitigation tests share one implementation — two would make the comparison meaningless"],
    ["ADR-006", "Strip identity at the proxy, fail closed", "The threat model states the proxy as the trust boundary; the guarantee is conditional on it"],
    ["ADR-007", "Propagate the salt to the engine, not just the EPP", "FR-B-05 gains a third obligation; the residual shrinks to 'whatever survives partitioning both'"],
    ["ADR-009", "SGLang as ATTEST's control arm", "D-06 amended: caching pinned off for vLLM because of an upstream integration gap, not determinism itself"],
    ["ADR-011", "No client-observable oracle on the simulator; FR-B-03 rescopes", "The attacker-observable oracle becomes FR-B-09's problem, on real vLLM"],
    ["ADR-012", "FR-B-03 measured: the leak exists and the salt closes it", "The two-profile diff is now backed by a measurement, not an argument"],
  ], 0.5, 1.3, 9.0, [1.1, 4.1, 3.8], 8);
}

// ---------- 24 Appendix: process stats and lessons
{
  const s = base("Appendix B — Build statistics and lessons", "Appendix");
  table(s, [
    ["Item", "Count", "Where"],
    ["ADRs", "12", "docs/design/decisions.md"],
    ["Findings logged (F-01…F-27)", "27", "STATE.md"],
    ["Findings that were guards containing their own defect", "4 (F-14, F-23/24, F-25, F-26)", "STATE.md, SHIP-REPORT.md §2"],
    ["Python tests", "332 (331 passing on this host, 1 Windows-only failure)", "uv run pytest -q"],
    ["Go tests (barrier/epp)", "19 functions / 26 with subtests, all passing", "go test ./... -v"],
    ["BARRIER cluster CI runs observed", "active, both profiles, since 2026-09-07", "gh run list -R roshanrana/PROVENANCE"],
  ], 0.5, 1.3, 9.0, [3.6, 3.0, 2.4], 8.3);
  box(s, 0.5, 3.55, 9.0, 1.35, "Lessons written into the record", "• A limit that has not been re-tested is a guess (ADR-008 — the Go toolchain 'block' was asserted, not tested, and blocked nothing once actually tried).\n• A gate whose failure message is silence cannot distinguish the thing it exists to catch (F-25).\n• An ignore-list only excludes the noise you already named — S-02 needed a property test, not a longer list (F-23/F-24).\n• Four instances of one shape is a pattern worth naming, not four coincidences.", { bs: 8.7 });
}

// ---------- 25 Appendix: repository map
{
  const s = base("Appendix C — Repository map and how to run", "Appendix");
  s.addText(["common/stats/      AUC, bootstrap CI, permutation, decision rule", "attest/harness/    matrix, ledger, engine client, vLLM + SGLang", "attest/receipt/    in-toto schema, JCS, ed25519, verify CLI", "attest/analysis/   divergence tables, cost-of-determinism CIs", "barrier/attack/    S-02 spike, FR-B-03 probe, ground truth", "barrier/epp/       Go: tenant-salt plugin + custom EPP binary", "barrier/deploy/    kind + Helm: values-default vs values-hardened", "bench/results/     immutable raw output, every number's source", "metrics/           headline.json, render.py (drift-checked)", "docs/design/       requirements, HLD, LLD, decisions, spikes", "docs/tasks/        early task packs (waves 1-2)", ".github/workflows/ ci.yml (disabled), barrier.yml (active)"].join("\n"), { x: 0.5, y: 1.3, w: 5.6, h: 3.3, fontFace: "Courier New", fontSize: 8.5, color: INK, isTextBox: true, margin: 0, valign: "top" });
  card(s, 6.3, 1.3, 3.2, 3.55, CARD_D, CARD_D);
  s.addText("Run it", { x: 6.45, y: 1.38, w: 3, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: MINT, isTextBox: true, margin: 0 });
  s.addText(["uv sync", "make check          # 332 Python", "                    # + Go, ~2 min", "make attest-demo    # full pipeline,", "                    # incl. tamper test", "make barrier-diff   # the mitigation,", "                    # as a diff", "", "# needs Docker + kind, no GPU", "make barrier-up PROFILE=hardened", "make barrier-spike", "", "# needs a real GPU", "make attest-stage1 \\", "  ENGINE_URL=http://host:8000"].join("\n"), { x: 6.45, y: 1.72, w: 3, h: 3.05, fontFace: "Courier New", fontSize: 8.5, color: WHITE, isTextBox: true, margin: 0, valign: "top" });
}

// ---------- 26 Close
{
  const s = dark("Questions", "PROVENANCE · roshanrana/PROVENANCE · design docs, decision log and bench/results in the repository");
}

pres.writeFile({ fileName: "C:/Code-Central/PROVENANCE/docs/pitch/provenance-architecture-deck.pptx" }).then((f) => console.log("wrote", f, "slides", n));
