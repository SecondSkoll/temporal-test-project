# ROADMAP

### Phase 1: Opencode Adoption
**Goal:** Replace direct LLM API calls with an opencode integration path while preserving workflow behavior and retry semantics.
**Requirements:** [OPC-01, OPC-02, OPC-03, OPC-04, OPC-05, OPC-06, OPC-07]
**Plans:** 7 plans

Plans:
- [ ] 01-01-PLAN.md - Define provider contract and migration guardrails
- [ ] 01-02-PLAN.md - Build opencode adapter and configuration surface
- [ ] 01-03-PLAN.md - Migrate llm activity call path to provider abstraction
- [ ] 01-04-PLAN.md - Migrate and expand tests for provider-based behavior
- [ ] 01-05-PLAN.md - Roll out runtime/charm/docs updates and verification
- [ ] 01-06-PLAN.md - Add real-LLM configuration profile and safe runtime controls
- [ ] 01-07-PLAN.md - Add real-LLM validation flow and CI-compatible guardrails
