# Intent Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Intent Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Intent Engine** used by the Voice (Jarvis) system in AI_OS.

The Intent Engine is responsible for mapping natural language user utterances (coming from Speech-to-Text) into clear, structured intents that the platform can safely execute or answer.

This document is subordinate to:

1. Voice (Jarvis) System Architecture  
2. Voice Configuration  
3. Agent Communication & Coordination Rules  
4. Workflow Architecture  

---

## 2. Design Goals

The Intent Engine must:

- Reliably map spoken language to platform intents
- Support a growing but controlled set of intents
- Handle ambiguity and low confidence gracefully
- Remain extensible as new capabilities are added
- Avoid becoming a free-form agent that bypasses the Workflow Engine
- Be observable

---

## 3. Core Responsibilities

- Accept recognized text from STT
- Classify the utterance into one or more candidate intents
- Extract relevant parameters / slots
- Return a structured intent result with confidence
- Support clarification when confidence is low or required parameters are missing
- Route the resolved intent to the correct platform action (via the Voice Integration Layer)

---

## 4. Intent Result Contract (Conceptual)

A resolved intent should contain:

- intent_id / intent_name
- confidence score
- extracted parameters (key-value)
- raw text
- alternative candidates (optional)
- whether clarification is required

---

## 5. Intent Categories (Initial)

Examples of intent categories the system should support:

- **Status & Query**
  - What is the status of workflow X?
  - Are there any pending approvals?
  - How much have we spent today?

- **Workflow Control**
  - Start a new product creation workflow
  - Cancel / pause a workflow (if allowed)

- **Human Approval**
  - Approve the pending architecture decision
  - Reject the current approval request

- **Experiment & Comparison**
  - Show me the latest LLM comparison results
  - Which model performed best on the last experiment?

- **System & Health**
  - Is the system healthy?
  - Which capability packs are active?

- **Help & Meta**
  - What can you do?
  - Help me with approvals

Exact intent catalog will evolve with the platform.

---

## 6. Key Design Rules

- The Intent Engine does **not** execute work itself; it only interprets and structures the request.
- High-impact intents must still pass through authorization and, when required, Human Approval Points.
- Ambiguous or low-confidence intents should trigger clarification rather than guessing.
- New intents should be added deliberately and documented.
- Capability Packs may contribute new intents related to their domain, but these must still be registered and governed.

---

## 7. Relationship with Other Components

- **STT Adapter** provides the input text.
- **Voice Session Manager** provides conversational context that can help disambiguation.
- **Platform Integration Layer** takes the resolved intent and turns it into concrete API / Workflow calls.
- **Workflow Engine** performs the actual work.
- **Configuration Manager** may control intent-related settings and thresholds.
- **Observability** records recognized intents and confidence for analysis and improvement.

---

## 8. Observability Requirements

Every intent recognition should record:

- Raw text
- Resolved intent and confidence
- Extracted parameters
- Whether clarification was required
- Subsequent action taken
- Correlation with Trace ID / Workflow ID when an action is triggered

---

## 9. Current Status

This document defines the design baseline for the Intent Engine.

Concrete intent catalog, training / rule approaches, and parameter extraction strategies will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Voice (Jarvis) System Architecture  
2. Intent Engine Design  
3. Source Code
