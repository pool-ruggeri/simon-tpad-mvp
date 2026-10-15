# Simon–TPad MVP maintenance instructions

The user is Product Owner; ChatGPT is Technical Lead; Codex is Implementation Engineer.
Keep this a small, readable laboratory MVP. Use English for code, comments, documentation,
reports, and commits. Follow PO-001 through PO-005 in docs/DECISIONS.md.

- Hardware milliseconds are authoritative. Never mix host and T-Pad clocks for scientific RT.
- Automatic T-Pad TTL produces physical event markers. Never echo received events into
  software TTL commands. Do not add a software trigger path.
- Use Mode 5 once at setup. Do not reset the hardware timer during trials.
- Do not change firmware, sensitivity, FTDI settings, drivers, Windows settings, global
  Python packages, existing PsychoPy installations, or other repositories.
- Install packages only in `.venv`. Preserve raw acquisition and results on abort/error.
- PC keyboard controls instructions and Escape. Serial responses use Buttons 1 and 2;
  log all four physical buttons. HID support is planned, not implemented.
- Missing optical events invalidate trials; never manufacture an onset or RT.
- Keep stimulus offset and visual scheduling independent of responses.
- Update docs/PROJECT_HANDOFF.md with changes, evidence, limitations, and resume commands.
- Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
  Hardware validation requires direct evidence.
- Local commits are authorized. Use the PO-supplied or existing identity. The PO's M3
  request authorizes creation of PRIVATE `pool-ruggeri/simon-tpad-mvp`, adding origin,
  and pushing main with its existing history after publication checks. Do not publish
  data/secrets, force-push, change visibility, or modify unrelated repositories.
- Do not spawn sub-agents unless the user explicitly requests delegation.
