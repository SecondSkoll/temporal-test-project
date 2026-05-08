# Repository Layout

```text
temporal-docs-pipeline/
├── src/                       # Source code for the Python Temporal worker and workflows
│   ├── workflows/             # Definitions for the Ingestion and Git Publisher workflows
│   │   ├── ingestion.py       # Workflow managing metadata parsing, cloning, and LLM generation
│   │   └── publisher.py       # Sequential workflow strictly managing Git index updates
│   ├── activities/            # Discrete Temporal activities
│   │   ├── git_ops.py         # libgit2 (pygit2) operations for shallow clones and PAT authentication
│   │   ├── triage.py          # os/glob heuristics to extract Readmes, docs/, and Makefiles
│   │   └── llm.py             # Integration with the OpenAI-compliant generation endpoint
│   ├── models/                # Pydantic data models for metadata ingestion and Temporal payloads
│   └── main.py                # Entry point to register workflows/activities and start the Temporal worker
├── config/                    # Configuration files for heuristics and prompts
│   ├── llm_prompt_templates.yaml # System prompts enforcing Canonical-specific documentation rules
│   └── triage_config.json     # Heuristics for shallow clone limits and glob file extensions
├── tests/                     # Test suite
│   ├── unit/                  # Unit tests for os/glob triage, prompt formatting, and pygit2 callbacks
│   └── integration/           # End-to-end tests using the mock Temporal and OpenAI servers
├── tools/                     # Scripts for local development and testing
│   ├── mock_openai_server.py  # Local FastAPI mock for the OpenAI API
│   └── trigger_workflow.py    # CLI tool to manually push mock package metadata into the Temporal cluster
├── charm/                     # Juju charm configuration
│   └── src/charm.py           # The Charmed Operator framework code for deploying the Temporal worker
├── requirements.txt           # Python dependencies (temporalio, openai, pydantic, pygit2, etc.)
└── README.md                  # Project overview, setup instructions, and architecture diagram
```
