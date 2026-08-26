---
description: Strict security rule forbidding the cleartext display or echoing of secrets, tokens, and credentials.
globs: ["*"]
---

# STRICT SECRET REDACTION POLICY

Under NO circumstances may full API keys, tokens, secrets, private keys, passwords, or credentials be output in cleartext in chat messages, artifacts, logs, or reports.

### Mandatory Rules:
1. **Redact All Secret Values**: Always mask secret values so that at most the prefix/provider and last 4 characters are visible (e.g. `sk-or-v1-...636a`, `AIzaSy...11Wk`, `rnd_...YNB`, `XXNAN...vRp`).
2. **Audit Reporting Format**: When inspecting or reporting on configuration files (`.env`, config YAMLs, etc.), report only:
   - Variable Name (e.g. `BINANCE_TESTNET_API_KEY`)
   - Presence Status (`[CONFIGURED]` / `[MISSING]`)
   - Masked representation with last 4 characters (e.g. `...s2vRp`)
3. **Never Echo Unmasked Strings**: Even if the user pastes a raw key or asks to view a `.env` section containing keys, you must mask the sensitive credential values in the output.
