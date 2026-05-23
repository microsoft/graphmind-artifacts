# Taxonomy Retry Prompt

**Pipeline Stage:** Stage 3 — Pruning and Alignment (Taxonomy Repair)  
**Agent Name:** `ExtractTaxonomy`  
**Called by:** `ExtractTaxonomy.exec()` (iterative retry loop)  

## Description

This prompt is used in a retry loop when the initial taxonomy extraction is missing actions or contains extra actions not present in the action list. It is appended to the conversation history and iterated up to 5 times until all actions are accounted for.

## Template Variables

- `{missing_action_text}` — Formatted list of action IDs still missing from the taxonomy
- `{', '.join(extra) if extra else 'None'}` — Comma-separated list of extra action IDs that should not be included

## Prompt

```
The following actions from the complete Action List are still **missing** from the taxonomy:

######################
{missing_action_text}
######################

The following actions are **extra** and should NOT be included in the taxonomy:
######################
{', '.join(extra) if extra else 'None'}
######################

Please regeenrated the taxonomy to include all the actions.
Return only the updated taxonomy in valid JSON.
```
