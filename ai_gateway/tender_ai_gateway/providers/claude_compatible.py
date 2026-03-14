from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeCompatibleProvider:
    name: str
    base_url: str
    supports_ccswitch: bool = False

