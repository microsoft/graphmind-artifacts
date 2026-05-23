# Find Text Between Actions Prompt

**Pipeline Stage:** Stage 1 — Data Preprocessing (Text Extractor)  
**Agent Name:** `ExtractImageDescription`  
**Called by:** `ExtractImageDescription._find_text_between_actions()`  

## Template Variables

- `{text}` — The full text containing both actions
- `{action_a["output"]}` — The output field of the first action
- `{action_b["output"]}` — The output field of the second action

## Prompt

```
You are a precise text extractor.

Given the following text and two known actions that occurred within it, identify and return the **exact portion of text between the two actions**.

Each action has a known command or code block in its `output`. Use these to locate their positions and return the full span of text between them **as-is** from the original source. If either action cannot be found, return an empty string.

### Full Text:
{text}

### Action A Output:
{action_a["output"]}

### Action B Output:
{action_b["output"]}

### RESPONSE FORMAT
```json
{
  "between_text": "<text between action A and action B>"
}
```
If either output is not found, return:
```json
{
  "between_text": ""
}
```
```
