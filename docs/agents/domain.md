# Domain docs

This is a single-context repository.

## Before exploring

- Read the root `GLOSSARY.md` when it exists.
- Read relevant records in `docs/adr/` when that directory exists.
- If these files do not exist, proceed without flagging their absence. Add them when a domain term needs clarification or a consequential design decision needs recording.

## Layout

```text
/
├── GLOSSARY.md
└── docs/
    └── adr/
```

Use established glossary terms in issue titles, plans, tests, and documentation. When an implementation conflicts with an ADR, surface the conflict instead of silently replacing the decision.
