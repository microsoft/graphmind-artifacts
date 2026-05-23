# Generate Labels for Taxonomy Prompt

**Pipeline Stage:** Stage 3 — Pruning and Alignment (Label Generator)  
**Agent Name:** `gen_labels_for_taxonomy`  
**Called by:** `gen_labels_for_taxonomy()` inner function in `extract_taxonomy_from_dict()`  

## Template Variables

- `{json.dumps(path, indent=2)}` — JSON representation of the taxonomy path (list of nodes) to generate labels for

## Prompt

```
You are an expert at creating concise, specific titles for technical troubleshooting steps.

INSTRUCTIONS:
- Given a sequence of nodes that described an incident resolution path, for each node, generate SHORT titles (5-10 words max) for EACH node to describe its function or purpose (for action nodes) or a short summary (for problem nodes).
- Each title should be clear and technical. DO NOT INCLUDE ANY ticket-specific info, such as incident numbers or action IDs, session ID, database IDs because those would change based on the context. A title such as "Session 50 is slow" is NOT acceptable.
- The goal is to make the label informative to help understand its functionality or give a quick summary.
- Do not add any ID (such as Session ID) in the title, use general term such as "a session" instead.

### GUIDELINE EXAMPLES BY NODE TYPE:
- **Problem nodes**: Focus on the specific symptom or failure (e.g., "ExternalDataSource CSV Load to SQL Pool Times Out")
- **Action nodes**: Describe the objective of the action, what it is doing (e.g., "[KQL] Query Failed Requests from AlertSqlErrorsTable", "[CAS] Invoke-MakeDbAccessible"), instead of the outcome or observation.
- **Mitigation nodes**: Focus on the solution or root cause (e.g., "Increased Connection Pool Size", "Configuration Error in Web.config")

### NODES TO LABEL:
{json.dumps(path, indent=2)}

### OUTPUT FORMAT:
Return a JSON object mapping the node's identifying field (problem, action_id, or incident_id) to its generated title:
{
  "problem_0_23414124": "Short title for the first problem node",
  "action_0_20393021": "Short title for action node",
  "action_1_20393022": "Short title for action node",
  "problem_1_2342341242": "Short title for the second problem node",
  "action_3_20393023": "Short title for action node",
  "action_mitigation_20393024": "Short title for mitigation node",
  ...
}

For problem nodes, use a generated ID like "problem_X_Y" where X is the sequence number.
For action nodes, use the action_id field value.
For mitigation nodes, use the action_id field value.
Skip incident_id nodes - don't generate labels for them.

Generate concise, specific titles now:
```
