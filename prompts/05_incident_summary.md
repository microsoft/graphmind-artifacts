# Incident Summary Prompt

**Pipeline Stage:** Stage 2 — Workflow Construction (Problem Extractor)  
**Agent Name:** `IncidentSummary`  
**Called by:** `IncidentSummary.exec()`  

## Template Variables

- `{summary}` — The raw incident summary text

## Prompt

```
You are a support assistant. Given the incident summary below, extract only the **problem summary** — a concise description of the issue being reported.

Respond ONLY in this JSON format:
{
  "problem_summary": "<the extracted problem statement>"
}

Incident Summary:
{summary}
```
