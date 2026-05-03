TASK_PROFILES = {
    "generate_section": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-max",
        "max_tokens": 8192,
    },
    "review_section": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-max",
        "max_tokens": 8192,
    },
    "tag_clauses": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 32768,
        "max_retries": 0,
    },
    "extract_tender_requirements": {
        # Single-pass full extraction uses flash for speed (~10-20 min for
        # an entire tender package).  v4-pro + max thinking was too slow per
        # batch (15-25 min @ 200 chunks) and hit the 1200 s timeout.
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "deepseek-v4-pro",
        "timeout": 2400,
        "max_tokens": 65536,
        "max_retries": 0,
    },
    "extract_tender_facts": {
        "primary_model": "deepseek-v4-pro",
        "fallback_model": "deepseek-v4-flash",
        "timeout": 600,
        "max_tokens": 8192,
        "max_retries": 0,
    },
    "extract_scoring_criteria": {
        "primary_model": "deepseek-v4-pro",
        "fallback_model": "deepseek-v4-flash",
        "timeout": 600,
        "max_tokens": 16384,
        "max_retries": 0,
    },
    "standard_parse_audit": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 900,
        "max_tokens": 65536,
        "max_retries": 0,
    },
    "clause_enrichment_batch": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 32768,
        "max_retries": 0,
    },
    "unparsed_block_repair": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 16384,
        "max_retries": 0,
    },
    "vision_repair": {
        "primary_model": "Qwen/Qwen3-VL-8B-Instruct",
        "fallback_model": "Qwen/Qwen3-VL-8B-Instruct",
        "timeout": 300,
        "max_tokens": 4096,
        "max_retries": 1,
    },
}
