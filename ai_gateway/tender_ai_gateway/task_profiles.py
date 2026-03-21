TASK_PROFILES = {
    "generate_section": {
        "primary_model": "deepseek-chat",
        "fallback_model": "qwen-max",
    },
    "review_section": {
        "primary_model": "deepseek-chat",
        "fallback_model": "qwen-max",
    },
    "tag_clauses": {
        "primary_model": "deepseek-chat",
        "fallback_model": "qwen-plus",
        "timeout": 180,
        "max_retries": 0,
    },
}
