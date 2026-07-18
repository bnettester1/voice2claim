# Voice2Claim Architecture

## 5-Layer Pipeline

1. **Layer 1: VALSEA ASR** - Speech-to-Text (mandatory)
2. **Layer 2: Speech Understanding** - Semantic API + LLM
3. **Layer 3: AI Workflow Planner** - Decides actions & order
4. **Layer 4: MCP Action Executor** - Executes actions
5. **Layer 5: Voice2Claim Dashboard** - UI for users

See diagram in README.md
