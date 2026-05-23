# Extract Results Chunk Prompt

**Pipeline Stage:** Stage 2 — Workflow Construction (Resolution Extractor)  
**Agent Name:** `ExtractResultsChunk`  
**Called by:** `ExtractResultsChunk.exec()`  

## Template Variables

- `{description_instance}` — The annotated text chunk (with `<action>action_id</action>` tags)
- `{chunk_actions}` — The list of action objects extracted for this chunk

## Prompt

```
You are an expert in extracting structured results from annotated incident descriptions.

Your task is to analyze a **description instance** that contains one or more actions annotated in the form `<action>action_id</action>`, and a corresponding list of actions. For each action, extract the **result** that appears immediately **after** it in the text. Each result can be one of:
 - **Tables**, such as outputs from KQL, SQL, or similar queries.
 - **Image Descriptions**, such as those surrounded by `<image_description>...</image_description>` tags.

Each extracted result must be:
1. **Described in natural language** (what it is, what it shows).
2. **Classified** by type (see detailed types below).
3. **Captured** in verbatim as visible text or content.

### ANNOTATION RULES:
- For **Tables**: You must also annotate the original description instance by wrapping each extracted result in `<result>description</result>`, where `description` is your generated explanation of that result.
- For **Image Descriptions**: Only replace the `<image_description>` tags with `<result>` tags in text and maintain the original description. In the output JSON, leave the `extracted_text` field as empty.
- The `text` field in the output **must include the entire original `INCIDENT TEXT INPUT` from start to end**, with the **only modification** being the insertion of `<result>...</result>` tags around detected results. Do **not remove or alter any other part** of the original text.

### RESULT TYPES:
Use the following detailed classifications for each result:
- `"kql_query_result"` — for outputs from Kusto Query Language (KQL) queries.
- `"sql_query_result"` — for outputs from SQL queries.
- `"cas_query_result"` — for outputs from CAS (Customer Analytics Services) queries.
- `"powershell_result"` — for outputs from PowerShell commands or scripts.
- `"python_result"` — for outputs from Python scripts or code execution.
- `"bash_result"` — for outputs from Bash/Shell commands.
- `"api_response"` — for API call responses or REST endpoint results.
- `"dashboard_screenshot"` — for dashboard visualizations or monitoring screenshots.
- `"metrics_data"` — for performance metrics, telemetry, or monitoring data.
- `"log_output"` — for system logs, error logs, or diagnostic logs.
- `"configuration_data"` — for configuration files, settings, or parameter outputs.
- `"error_message"` — for error messages, exceptions, or stack traces.
- `"system_message"` — for system notifications or status messages.
- `"auto_assignment"` — for the text blobs that starts with "This incident is auto-assigned ...".
- `"diagnostic_result"` — for outputs from diagnostic tools or health checks.
- `"resource_status"` — for resource status information (CPU, memory, disk, network).
- `"schema_info"` — for database schema or table structure information.
- `"other_result"` — for any other kind of result that doesn't fit the above categories.

### OUTPUT FORMAT:
Return a JSON object with the following structure:

{
  "actions": [
    {
      "id": "<action id from passed actions>",
      "type": "<some result type>",
      "output": {
        "description": "<natural language explanation of what the action's effect or purpose>",
        "extracted_text": "<verbatim snippet from the original text>"
      },
      "actor": "<actor name, extracted from the action's metadata (e.g., 'ChangedBy')>"
    },
    {
      "id": "<unique id for this auto-assignment>",
      "type": "auto_assignment",
      "output": {
        "description": "This incident is auto-assigned [rest of the text]",
        "extracted_text": "verbatim visible result content"
      },
      "actor": "icmautosvc"
    },
    {
      "id": "<unique id for this action>",
      "type": "auto_assignment",
      "output": {
        "description": "We don't find any output after this action.",
        "extracted_text": "We don't find any output after this action."
      },
      "actor": "icmautosvc"
    },
    ...
  ],
  "text": "<FULL VERSION of the original `INCIDENT TEXT INPUT`, with only <result>...</result> tags added around results>"
}

### INSTRUCTIONS:
- Process the text in the order of actions provided.
- If no valid result is found for an action, output `null` for that result.
- Be comprehensive, but only use **explicit content from the text**—do not hallucinate or infer.
- Ensure that the `text` field is a fully preserved copy of `INCIDENT TEXT INPUT`—**only** modified by the insertion of `<result>` tags.
- When classifying results, look for contextual clues:
  - Mentions of "KQL", "Kusto", ".kusto.windows.net" → `kql_query_result`
  - Mentions of "SQL", "SELECT", "INSERT", "UPDATE" → `sql_query_result`
  - Mentions of "CAS", "Customer Analytics" → `cas_query_result`
  - Mentions of "PowerShell", "PS", "Get-", "Set-" → `powershell_result`
  - Mentions of "python", ".py", "import" → `python_result`
  - Mentions of "bash", "sh", shell commands → `bash_result`
  - Mentions of "API", "endpoint", "HTTP", "REST" → `api_response`
  - Mentions of "dashboard", "visualization", "chart" → `dashboard_screenshot`
  - Mentions of "metrics", "telemetry", "performance" → `metrics_data`
  - Mentions of "log", "trace", "debug" → `log_output`
  - Mentions of "config", "settings", "parameters" → `configuration_data`
  - Mentions of "error", "exception", "failed" → `error_message`
  - Mentions of "CPU", "memory", "disk", "network" usage → `resource_status`
  - Mentions of "schema", "table structure", "columns" → `schema_info`

### LONG RESULT HANDLING:
- If the result block is large (e.g., a long table), treat the post-`<action>` text as **line-based output**.
- Identify the full block, even if it spans multiple lines, and include it in the extraction and tagging.
- Please ensure that each action has a corresponding result block extracted, even if it is large or none. If no results are found, put "We don't find any output after this action." as the extracted_text.

### INCIDENT TEXT INPUT:
{description_instance}

### ACTIONS INPUT:
{chunk_actions}
```
