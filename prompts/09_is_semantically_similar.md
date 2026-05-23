# Semantic Similarity Prompt

**Pipeline Stage:** Stage 3 — Pruning and Alignment (Semantic Similarity)  
**Agent Name:** `is_semantically_similar`  
**Called by:** `is_semantically_similar()` function  

## Template Variables

- `{res1}` — First resolution string
- `{res2}` — Second resolution string

## Prompt

```
You are an expert in semantic matching analysis. Your task is to assess whether the following two resolutions express the **same underlying meaning**, even if they are phrased differently.

Respond with **only** "YES" or "NO".

**Resolution A:**
{res1}

**Resolution B:**
{res2}

Do these two resolutions convey the same intent or outcome?
```
