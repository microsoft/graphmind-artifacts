# Extract Taxonomy Prompt

**Pipeline Stage:** Stage 2 — Workflow Construction (Workflow Extractor)  
**Agent Name:** `ExtractTaxonomy`  
**Called by:** `ExtractTaxonomy.exec()`  

## Template Variables

- `{action_chain}` — Chronological list of action IDs the LLM must preserve (`[{"action": "action_0"}, ...]`)
- `{merged_actions}` — List of action-and-result pairs (full action detail + optional result)
- `{self.shared["icm_number"]}` — The incident number
- `{self.shared["output_format"]}` — The required JSON output format (see below)
- `{icm}` — The full annotated incident text

### Output Format Template

The `{self.shared["output_format"]}` variable is populated with:
```json
{
  "domain": "<domain_name>",
  "taxonomy": [
    {
      "incident_id": "<incident_number>"
    },
    {
      "problem": "<clear description of observed issue>"
    },
    {
      "action": "<exact action from provided action list>"
    },
    {
      "observation": "<observable result if any>"
    },
    {
      "action": "<corresponding action taken>"
    },
    ...
    {
      "cause": "<explicitly stated root cause if available>"
    }
  ]
}
```

## Prompt

```
You are an expert in taxonomy extraction for Incident Management and Root Cause Analysis based on ACTION INPUT and OUTPUT.

Your task is to inject problem, observation, and cause/resolution nodes into the existing taxonomy (action chain) given the E2E incident triaging process from the original incident transcript.
Your taxonomy must follow this **exact linear sequence** to generate ONE new chain end-to-end:

**Problem → Action → (Observation → Action → …) → Problem → Action → (Observation → Action → …) → [Cause or Resolution]**

### INSTRUCTION
1. Only insert problem nodes: (1) at the beginning of the chain or (2) after an incident transfer action as this transfer triggers a new investigation process with a potential new problem to triage.
    - This problem node should include the description about the information available "so far". For instance, the first problem node should include a short description about the incident. And the problem node right after an transfer incident action should include the description about the observations and findings so far.
    - For the problem node after an transfer action, please start the problem description with "After transferring to <team name>,", where <team name> is the team AFTER the transfer happens.
2. Insert observation nodes: (1) after each action if there is a result available from the action taken. The observation should describe what was found from the result of the action taken.
3. Please ensure that each action is preceded by a **Problem** or **Observation**. Standalone actions are invalid and must be excluded. It has to be Problem→Action or Observation→Action. Each action should have a good reason/trigger to trigger it.
4. Extract domain (the team name) based on the first incident transfer action in the taxonomy (after the "from" keyword). This is the first team handling the incident. Put it in the domain field. If no incident transfer actions are found, use "Unknown".
5. You should confirm that every action ID present in the taxonomy is exactly listed in the `ACTION INPUT` and the actions in the taxonomy follows the same action order (from small action ids to larger, keep the original input order). Do not include any action IDs that are not in the `ACTION INPUT`.
6. At the end, add a Cause or Resolution (only one of them).

### NODE DEFINITIONS
- **Problem**: An explicitly stated issue, error, anomaly, or abnormal condition mentioned in the `INCIDENT TEXT INPUT`. Try to be specific about the "symptom" or "issue" being investigated SO FAR. Don't include ticket-specific information such as region, database IDs. The problem statement will be used as a search index to look for relevant actions to take based on observations/symptoms so far. If the problem node is after an incident transfer node, starting this problem description with "After transferring to <team name>," from the actions before this. Do not include any 'future' observation. Only include descriptions based on the nodes before. Use around 200 characters to describe the problem.
- **Action**: A clearly described intervention taken in response to a Problem. All valid actions are passed in the `ACTION INPUT`.
- **Observation**: The result from the action taken (if available).
- **Cause** *(optional)*: An explicitly stated root cause or underlying reason identified in the discussion in `INCIDENT TEXT INPUT`. This represents the end of a root cause analysis path.
- **Resolution** *(optional)*: A definitive fix or mitigation step stated in the `INCIDENT TEXT INPUT`. This represents the end of an incident resolution path.

### EXTRACTION RULES — STRICTLY ENFORCED
1. All critical mitigations are explicitly annotated using the `<mitigation>...</mitigation>` tags in the `INCIDENT TEXT INPUT`. These **must always be treated as Resolutions** in the output taxonomy.
- However, do **not** limit Resolutions to only those tagged as `<mitigation>`. Carefully read the entire text for any other actions or events that clearly result in resolving or mitigating the incident, and include those as additional Resolutions when appropriate.
- Use contextual understanding to identify untagged resolutions, but **never invent or infer** resolutions not grounded in the provided text.
2. Use **only action IDs** in the taxonomy. Do not include full action descriptions or any other metadata.
3. Before adding an action to the taxonomy, cross-check its ID against the `ACTION INPUT` list. If the ID does not exist in that list, skip it. Do not attempt to normalize or guess.
4. Output must be a single, well-formed **JSON object** following the required output format. No commentary, markdown, or extra text is allowed — only raw JSON.

### CONTEXTUAL METADATA

- **Incident Number**: {self.shared["icm_number"]}

### CURRENT ACTION CHUNK BEING PROCESSED:
### EXISTING ACTION CHAIN
This is the action chain you must inject problem/observation/cause/resolution nodes into. **Every `action` ID below must appear in the output taxonomy, in this exact order. Do not drop or reorder any.**
```json
{action_chain}
```

### ACTION AND RESULT PAIRS
Each entry below corresponds to one action_id in the chain above, with the (optional) result of executing it. Use these details to write the surrounding Problem/Observation/Cause nodes.
{merged_actions}

### REQUIRED OUTPUT FORMAT
```json
{self.shared["output_format"]}
```

### FULL INCIDENT TEXT INPUT
{icm}

### INSTRUCTIONS
- Please separate the actions into one or more independent taxonomies based on the above rules and make sure each taxonomy is handled by a single team, inferred from incident transfer actions. Two paths by two team should not be merged.
- Please ensure the actions in the taxonomies follow the chronological order as action_1, action_2, action_3, etc. both with within each taxonomy and across taxonomies.
- Please ensure that incident transfer actions are only placed as the last action in the taxonomy paths.
- Please do not drop any actions.
- Please ensure to have observation or problem nodes before each action.
```
