"""Text cleaning, URL decoding, JSON extraction, and chunking helpers."""
import base64
import gzip
import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import unquote

import dirtyjson

from .llm_client import call_llm

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load the fenced prompt body from artifact/prompts/{name}.

    Each prompt file has the structure:
        ...preamble...
        ## Prompt
        ```
        <body>
        ```
    Returns the <body> exactly as written (template placeholders intact).
    """
    text = (_PROMPTS_DIR / name).read_text()
    _, _, after = text.partition("## Prompt")
    first = after.find("```")
    body_start = after.index("\n", first) + 1
    body_end = after.rfind("\n```")
    return after[body_start:body_end]

logger = logging.getLogger("graphmind")


def decode_adx_link(url: str) -> str:
    match = re.search(r'[?&]query=([^&]+)', url)
    if not match:
        return url
    q_encoded = match.group(1)
    q_decoded_url = unquote(q_encoded)
    try:
        missing_padding = len(q_decoded_url) % 4
        if missing_padding:
            q_decoded_url += '=' * (4 - missing_padding)
        raw_bytes = base64.b64decode(q_decoded_url)
        return gzip.decompress(raw_bytes).decode("utf-8")
    except Exception:
        prompt = (
            f"You are an expert KQL extractor. Given a URL that contains a KQL query, "
            f"extract and return the KQL query in plain text. If the URL does not contain "
            f"a valid KQL query, respond with the full url. If the url only contains link "
            f"to cluster but not any query predicates/table names, return 'unvalid url'\n"
            f"URL: {url}\n### OUTPUT FORMAT:\n```kql\n<Kusto Query>\n```"
        )
        q = call_llm(prompt, max_tokens=2000, agent_name="decode_adx_link").strip()
        return q.replace("```kql", "").replace("```", "").strip()


def clean_text(text: str) -> str:
    try:
        text = text.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        text = text.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        text = re.sub(r"\\[UuSs]\w{0,7}", "", text)
    text = re.sub(r"Execute:\s*(?:\[\s*[^\]]+\s*\]\s*)*(https?://\S+)?", "", text)
    text = re.sub(r"Open in(?:\s*\[[^\]]*\])+", "", text)
    text = re.sub(r"Execute in(?:\s*\[[^\]]*\])+", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    text = text.encode("ascii", errors="ignore").decode()
    text = re.sub(r"\\[^\ntrn\"'\\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def remove_tables(text: str, max_token: int = 2000) -> str:
    try:
        prompt = f"""You are an expert text cleaner specialized in processing technical logs and diagnostics. Your task is to identify and **remove long tabular data or query results**, especially those that appear after KQL or SQL queries.

### TASK INSTRUCTIONS:
1. **Remove all long tables** (typically multi-line outputs of query results).
2. **Preserve the surrounding narrative/context**.
3. **Keep the schema header of the removed table**, and annotate it with:
<observation>This query resulted in schema that starts with: [schema_columns]</observation>
4. Do **not** add explanations or modify other content.

### INPUT TEXT:
{text}

### OUTPUT FORMAT:
- Cleaned version of the input text with tables removed and schema preserved."""
        return call_llm(prompt, max_tokens=max_token, agent_name="remove_tables").strip()
    except Exception as e:
        logger.warning("remove_tables LLM call failed: %s. Returning original text.", e)
        return text


def extract_json_from_string(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            try:
                return dirtyjson.loads(match.group(1))
            except Exception:
                pass
    logger.warning("No valid JSON found in the string.")
    return None


def replace_img_tags_with_placeholders(text: str, shared: dict):
    if "image_index" not in shared:
        shared["image_index"] = 0
    if "images" not in shared:
        shared["images"] = {}

    def replacer(match):
        img_tag = match.group(0)
        img_id = f"IMG_{shared['image_index']}"
        shared["images"][img_id] = img_tag
        shared["image_index"] += 1
        return f"<img>{img_id}</img>"

    updated_text = re.sub(r"<img\b[^>]*>", replacer, text, flags=re.IGNORECASE)
    return updated_text, shared


def has_any_img_id_tag(text: str) -> bool:
    return re.search(r"<img>IMG_\d+</img>", text) is not None


def extract_img_ids(text: str) -> List[str]:
    return re.findall(r"<img>([^<>]+)</img>", text)


def extract_base64_image(html: str):
    match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", html)
    return match.group(1) if match else None


def remove_img_tags(obj):
    if isinstance(obj, dict):
        return {k: remove_img_tags(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [remove_img_tags(item) for item in obj]
    elif isinstance(obj, str):
        return re.sub(r"<img\b[^>]*>", "", obj)
    return obj


def remove_action_tags_for_filtered(text: str) -> str:
    matches = re.findall(r"<action>(.*?)</action>", text)
    filtered = [m for m in matches if ".windows.net/" in m]
    def untag(match):
        content = match.group(1)
        return content if content in filtered else match.group(0)
    return re.sub(r"<action>(.*?)</action>", untag, text)


def replace_action_tags_with_id(text: str, index: int) -> str:
    def replacer(match):
        nonlocal index
        replacement = f"<action>action_{index}</action>"
        index += 1
        return replacement
    return re.sub(r"<action>.*?</action>", replacer, text, flags=re.DOTALL)


def split_chain(elements: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    result, current_group, current_actor, seen_icmautosvc = [], [], None, False
    for element in elements:
        if element is None:
            continue
        actor = element.get("actor")
        if actor == "icmautosvc":
            seen_icmautosvc = True
            continue
        is_placeholder = actor is None or actor == "null"
        if current_group:
            if actor != current_actor and not seen_icmautosvc and not is_placeholder:
                result.append(current_group)
                current_group = []
        current_group.append(element)
        if not is_placeholder:
            if actor != current_actor:
                seen_icmautosvc = False
            current_actor = actor
    if current_group:
        result.append(current_group)
    merged = []
    for current in result:
        if len(current) < 3 and merged:
            merged[-1].extend(current)
        else:
            merged.append(current)
    return merged


def is_semantically_similar(res1: str, res2: str) -> bool:
    prompt = f"""You are an expert in semantic matching analysis. Assess whether the following two resolutions express the **same underlying meaning**.

Respond with **only** \"YES\" or \"NO\".

**Resolution A:**
{res1}

**Resolution B:**
{res2}

Do these two resolutions convey the same intent or outcome?"""
    response = call_llm(prompt, agent_name="is_semantically_similar")
    return response.strip().upper() == "YES"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def normalize_command(text):
    if not text:
        return ""
    normalized = re.sub(r'\s+', ' ', text.replace('\\n', ' ').replace('\\r', ' ')).strip()
    normalized = re.sub(r'\s*\(\s*', '(', normalized)
    normalized = re.sub(r'\s*\)\s*', ')', normalized)
    normalized = re.sub(r'\s*,\s*', ',', normalized)
    return normalized


def are_similar(str1, str2, threshold=0.95):
    if not str1 or not str2:
        return False
    return SequenceMatcher(None, str1, str2).ratio() >= threshold
