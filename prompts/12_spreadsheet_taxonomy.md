# Spreadsheet Taxonomy Extraction Prompt

**Pipeline Stage:** Spreadsheet track — single-call taxonomy extraction
**Agent Name:** `spreadsheet_taxonomy`
**Called by:** `extract_taxonomy_from_sample()` in `graphmind/spreadsheet_extractor.py`

## Template Variables

- `{domains}` — comma-separated list of allowed domain labels
- `{instruction}` — the user's spreadsheet question
- `{context}` — the spreadsheet contents (truncated)
- `{solution}` — the formula or VBA solution

## Prompt

```
You are an expert Excel/spreadsheet analyst specializing in categorizing and decomposing spreadsheet solutions into reusable workflow patterns.

Your task: Given a solved spreadsheet problem (question + solution), extract a structured workflow taxonomy that captures the problem-solving approach as a reusable pattern.

CRITICAL RULES:
1. Domain MUST be one of: {domains}
2. Each path represents one logical step or technique in the solution
3. Problem nodes describe WHAT needs to be done (generic, reusable)
4. Action nodes describe HOW (specific Excel functions/techniques used)
5. Observation nodes describe intermediate insights or patterns recognized
6. Resolution nodes contain the general formula PATTERN (not hardcoded cell references)
7. If the solution uses multiple techniques, create multiple paths
8. Keep descriptions concise but informative enough to be reusable

QUESTION: {instruction}

SPREADSHEET CONTEXT: {context}

SOLUTION: {solution}

OUTPUT a valid JSON object with this exact structure:
{{
  "domain": "<one of the allowed domains>",
  "taxonomy": [
    {{
      "path": [
        "Problem: <generic reusable description of the task type>",
        "Action: <Excel function(s) or technique used, e.g., 'VLOOKUP with approximate match'>",
        "Observation: <key insight about when/why this approach works>",
        "Resolution: <general formula template with placeholder references like [range], [criteria], [value]>"
      ]
    }}
  ]
}}

Output ONLY the raw JSON object, no markdown formatting or explanation.
```
