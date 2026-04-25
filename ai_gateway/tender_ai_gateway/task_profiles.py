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
