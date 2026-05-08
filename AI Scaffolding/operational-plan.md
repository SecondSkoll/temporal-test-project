# Operational Plan

## 1. Configuration Files

Before beginning development, we will establish two core configuration files to standardize the generation and triage processes:

*   **`llm_prompt_templates.yaml`**: This file contains the structured system prompts and instructions that the Python Temporal workflow will pass to the OpenAI-compliant endpoint. It will include specific directives to ensure the LLM strips generic OS information and strictly enforces Ubuntu/Canonical-specific paths, prerequisites, and retrieval methods based on the package metadata.
*   **`triage_config.json`**: A lightweight configuration defining the heuristics for the Python `os/glob` mechanical triage script. It will specify which file extensions (e.g., `.md`, `.txt`, `.rst`) and directory structures (e.g., `docs/`) to prioritize during extraction, as well as strict constraints for the shallow cloning process (e.g., maximum file sizes, timeout limits) to prevent system instability.

## 2. Agent Personas and Roles

To ensure high-quality execution and robust architecture, we will define distinct roles for the AI models and the system architecture:

*   **Antigravity (Lead Developer)**: The primary autonomous agent responsible for driving the implementation. Antigravity will iteratively write the Python Temporal workflows, spin up the local Temporal dev server and OpenAI mock, implement the `os/glob` triage logic, and handle Git PAT authentication.
*   **The Orchestrator (System Architecture Role)**: The operational philosophy for the Temporal system itself. This role demands strict decoupling: the "Ingestion" workflows handle data gathering (executing shallow clones and failing gracefully to a manual triage queue on size limits), while the "Publisher" workflow strictly manages sequential Git queuing, implementing robust retry defaults for index conflicts.

## 3. Adversarial Review Process

To eliminate blind spots and ensure the system's resilience, we will conduct adversarial reviews using a secondary model from a different provider.

*   **Secondary Model**: OpenAI GPT-4o (or Anthropic Claude 3.5 Sonnet).
*   **When to Invoke**: Reviews should be conducted at two critical milestones:
    1.  Upon completion of the Git Publisher workflow logic.
    2.  Upon finalization of the mechanical triage and LLM prompt integration.
*   **What to Review**: The secondary model will aggressively critique the Python codebase and Temporal activity definitions for:
    *   **Security**: Flaws in how Git Personal Access Tokens (PATs) are managed and utilized during the commit process.
    *   **Concurrency**: Edge cases in the retry logic for Git push failures to ensure race conditions do not corrupt the YAML/MD index file.
    *   **Resource Exhaustion**: Vulnerabilities in the shallow clone and `os/glob` traversal scripts that could lead to disk exhaustion or infinite loops when processing massive or malformed upstream repositories.
