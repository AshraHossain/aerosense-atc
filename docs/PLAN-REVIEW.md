# Plan Review — AeroSense ATC (council-driven)

> Branch `plan-review`, cut from `master`. Purpose: compare the system **as
> pitched** (AeroCommand) against the system **as built** (AeroSense ATC), and
> record how the plan should be updated before more code is written.

---

## The Council

```
═══════════════════════════════════════════════════════════════════
                         THE COUNCIL
   "How should the AeroSense ATC plan be updated for production?"
═══════════════════════════════════════════════════════════════════

⚔ THE ADVERSARY
The assumption you're burying is that this is a "12-phase DO-178C-compliant"
system. It has zero automated tests. DO-178C DAL-C requires documented
requirements-based testing with structural coverage — you have a hash function
and a JSONL file and you're calling it compliance. That's not a plan, that's a
hope. Before anyone debates CrewAI vs LangGraph, understand that a single Gemini
prompt change today can silently break emergency-squawk routing and nothing
would catch it. Fix the test vacuum or the rest is theater.

──────────────────────────────────────────────────────────────────

⚙ THE ENGINEER
The Adversary is right, and I'll make it concrete: your routing logic
(7700/7600/7500 bypass, alert-level conflict escalation, Phase-12 re-check loop)
is deterministic graph code — it is trivially unit-testable without spending a
token on Gemini. That is where the first 50 tests live, and they'll run in
milliseconds. On the pitched stack: Kafka + Postgres + Redis for a single-node
demo that compiles one graph at import time is over-engineering. You'd add three
operational dependencies to solve a throughput problem you do not have. Keep
LangGraph as the spine; CrewAI earns its place only at Phase 12 where it already
is. Don't rebuild to the pitch — the as-built design is the laizer, correct one.

──────────────────────────────────────────────────────────────────

🔬 THE SCIENTIST
Let's separate belief from fact. The claim "production-ready" is untested: you
have no eval set, so you cannot state a pass rate for Nominal/Conflict/Emergency
scenarios. The base rate for LLM agents silently regressing on a prompt or model
swap is high — this is exactly what model-upgrade tests exist to catch. The
smallest experiment that would update my confidence: 3 golden scenarios with
asserted structured outputs plus an LLM-judge on the supervisor brief. Until that
exists, "it works" is a hypothesis, not a result.

──────────────────────────────────────────────────────────────────

📈 THE STRATEGIST
For a portfolio targeting Boeing / Anduril / Palantir, the differentiator is not
"I used Kafka." It's "I built a safety-critical agentic system with a real eval
harness and an audit trail." That's the rare combination. The pitched rewrite to
the heavy stack is effort with no resume leverage — recruiters don't reward
infra you didn't need. The leverage point is depth on three things: traceability,
evals, and HITL approval. Ship those and the aviation-domain framing sells itself.

──────────────────────────────────────────────────────────────────

🎨 THE VISIONARY
You're playing the wrong game if the goal is "more agents." The 10x version is
narrower: make this the system that can prove *why* it made every decision.
Reframe the whole project around the audit trail you already started in Phase 11
— a glass-box ATC where every clearance is replayable from its trace. That is far
more impressive than seven more agents, and it turns your DO-178C bones into the
headline feature instead of a footnote.

──────────────────────────────────────────────────────────────────

🧘 THE PHILOSOPHER
The real question underneath this question: what does "compliant" obligate you
to? Borrowing DO-178C language for a demo without the rigor isn't just a test
gap — it's a claim about safety you can't currently back. Either earn the label
with requirements-traced tests, or soften it to "DO-178C-inspired" and be honest.
For an aviation portfolio, the integrity of that distinction is the thing a
serious reviewer will actually probe.

──────────────────────────────────────────────────────────────────

❤ THE HUMANIST
The person who has to maintain this is you, six months from now, mid-interview,
asked "walk me through how you tested the emergency path." Right now you'd have
no answer. Build the tests not as a chore but as the script for that
conversation. And the Human-Approval agent isn't a node — it's the admission
that a machine shouldn't autonomously divert 130 flights. Make that boundary real
and visible; it's the most human, most senior thing in the whole design.
```

---

## The Verdict

```
═══════════════════════════════════════════════════════════════════
                         THE VERDICT
═══════════════════════════════════════════════════════════════════

POSITION: Keep the as-built LangGraph + Gemini design — do NOT rewrite to the
Kafka/Postgres/Redis/CrewAI-first pitch — and spend the next phases on tests,
evals, tracing, and HITL, in that order.

CONFIDENCE: 80% — The as-built architecture is the correct, lazier choice for a
single-node demo, and the test/eval gap is unambiguous. What moves this to 90%:
seeing the first 50 routing tests green and one eval scenario asserting a pass
rate.

──────────────────────────────────────────────────────────────────

CRITICAL RISKS  (exactly 3)

  1. **Compliance-Claim Gap**: Marketing "DO-178C compliance" with zero
     requirements-based tests is the one thing a serious aviation reviewer will
     catch instantly and hold against the whole project.
  2. **Silent LLM Regression**: With no eval harness, any Gemini prompt or model
     version change can break safety routing with no signal until a demo fails.
  3. **Rewrite Trap**: Burning weeks porting to Kafka/Postgres/Redis adds
     operational surface area, no resume value, and delays the work that matters.

──────────────────────────────────────────────────────────────────

NEXT STEPS  (exactly 5, in order of priority)

  1. Write ~50 deterministic tests for graph routing and ATCState schema —
     no LLM calls, runs in milliseconds. This is the highest-ROI work and unblocks
     safe refactoring.
  2. Build a 3-scenario eval harness (Nominal/Conflict/Emergency) with asserted
     structured outputs plus an LLM-judge on the supervisor brief; record a pass
     rate.
  3. Wire real tracing (LangSmith or OpenTelemetry) onto every phase so each
     retrieval, reasoning step, and tool call is replayable from the trace.
  4. Make the Human-Approval node a real HITL gate with an explicit
     approve/escalate decision and audit entry, not a pass-through.
  5. Decide and document the honest compliance label ("DO-178C-inspired" until
     requirements traceability exists), then finish the Docker container.

──────────────────────────────────────────────────────────────────

MINORITY REPORT: 📈 THE STRATEGIST
"There's a version where the heavy stack is worth it — if the story you're
selling is 'distributed event-driven systems engineer,' Kafka on the resume opens
doors LangGraph doesn't. Just know you're optimizing for a different job than the
agentic-AI one this codebase actually demonstrates."
```

---

## Plan as Pitched vs. Plan as Built

| Dimension | Pitched (AeroCommand) | As built (AeroSense ATC) | Verdict |
|---|---|---|---|
| Orchestration | CrewAI-first, 7 agents | LangGraph 12-phase graph, CrewAI only at Phase 12 | **Keep as-built** — LangGraph is the right spine; don't invert |
| Model | (impl-unstated) | Google Gemini | Keep; add model-upgrade regression tests |
| State store | PostgreSQL | In-memory `ATCState` over the graph | Keep for single-node; revisit only at multi-node scale |
| Eventing | Apache Kafka | In-process event bus | **Drop Kafka** — no throughput need; over-engineering |
| Memory | Redis | local dirs (gitignored stores) | Keep |
| Observability | LangSmith + Prometheus | DO-178C hash traces, `traces/*.jsonl`, no live spans | **Gap** — wire real tracing (step 3) |
| Tests | (unstated) | **0 test files** | **Critical gap** — fix first (step 1) |
| HITL | Human Approval agent | node exists, behaviour unverified | **Gap** — make it a real gate (step 4) |
| Compliance | "DO-178C" | hashing only, no requirements traceability | **Relabel honestly** until earned (step 5) |
| Deployment | Docker | `docker/` dir, partial | Finish container (step 5) |

## How the plan needs to be updated (one line)

Stop adding agents and stop chasing the heavy infra stack; convert the existing
12-phase graph into a **tested, evaluated, traceable, human-gated** system —
because for a safety-critical aviation AI portfolio, provable correctness beats
architectural surface area every time.
