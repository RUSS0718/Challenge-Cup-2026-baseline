# Triage labels

The triage workflow uses five canonical state labels. Their strings match the role names used by the local Matt Pocock triage skill.

| Triage role | GitHub label | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | A maintainer needs to evaluate the request. |
| `needs-info` | `needs-info` | The reporter needs to provide more information. |
| `ready-for-agent` | `ready-for-agent` | The request is specified and ready for agent implementation. |
| `ready-for-human` | `ready-for-human` | The request needs human implementation or judgment. |
| `wontfix` | `wontfix` | The request will not be actioned. |

Triage also classifies the request as `bug` or `enhancement`; those are category roles, separate from the five workflow state labels.
