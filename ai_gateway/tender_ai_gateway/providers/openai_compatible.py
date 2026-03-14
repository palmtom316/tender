from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    name: str
    base_url: str
    supports_ccswitch: bool = False

