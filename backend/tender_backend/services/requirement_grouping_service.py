"""Group extracted tender requirements into engineer-friendly review packages."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


CRITICAL_CATEGORIES = {"veto", "qualification", "performance", "project_team", "personnel"}
REVIEW_CATEGORIES = {"scoring", "technical", "format", "business", "contract", "special", "schedule"}
ORDINARY_AUTO_ACCEPT_CATEGORIES = {"technical", "contract", "format", "business", "project_info"}

LANE_LABELS = {
    "project_basics": "项目基本盘",
    "red_lines": "废标红线",
    "qualification_business": "资格商务硬条件",
    "technical_response": "技术响应重点",
    "submission": "递交清单",
    "sampling": "自动采纳抽查",
    "ignored": "已忽略/仅归档",
}

TOPIC_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("bid_bond", ("保证金", "投标担保", "保函")),
    ("deadline", ("截止", "开标", "递交", "上传", "解密")),
    ("signature", ("签章", "盖章", "签字", "电子签名", "CA")),
    ("copy_count", ("正本", "副本", "份数", "电子版", "U盘", "密封")),
    ("qualification", ("资质", "许可证", "证书", "一纸证明")),
    ("social_security", ("社保", "缴纳")),
    ("performance", ("业绩", "类似工程", "合同业绩", "竣工验收")),
    ("file_size", ("文件大小", "MB", "M以内", "大小限制")),
    ("scoring", ("评分", "分值", "评审")),
    ("technical", ("技术", "施工方案", "质量", "安全", "进度")),
]

KEY_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "date": re.compile(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?|\d{1,2}月\d{1,2}日|\d{1,2}:\d{2}"),
    "amount": re.compile(r"\d+(?:\.\d+)?\s*(?:万元|元|人民币|%)"),
    "copy_count": re.compile(r"(?:正本|副本|电子版|U盘|纸质)\s*\d+\s*份|\d+\s*份"),
    "certificate_grade": re.compile(r"(?:一级|二级|三级|四级|五级|甲级|乙级|丙级|[一二三四五]级)"),
    "social_security_months": re.compile(r"\d+\s*个?月"),
    "file_size": re.compile(r"\d+(?:\.\d+)?\s*(?:MB|M|GB|G)"),
}


def _text(row: dict[str, Any]) -> str:
    return str(row.get("requirement_text") or row.get("source_text") or row.get("title") or "")


def _compact(value: str) -> str:
    return " ".join(value.split())


def _normalise_for_key(value: str) -> str:
    text = _compact(value).lower()
    text = re.sub(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?", "#date", text)
    text = re.sub(r"\d+(?:\.\d+)?", "#num", text)
    text = re.sub(r"[\s，。；;:：、,.()（）\[\]【】《》<>\"'“”‘’]+", "", text)
    return text[:48]


def _topic(text: str) -> str | None:
    for topic, keywords in TOPIC_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return topic
    return None


def _extract_key_fields(text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for name, pattern in KEY_FIELD_PATTERNS.items():
        values = sorted(set(match.group(0).replace(" ", "") for match in pattern.finditer(text)))
        if values:
            fields[name] = values
    return fields


def _merge_key_fields(rows: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[str]]:
    collected: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for name, values in _extract_key_fields(_text(row)).items():
            collected[name].update(values)
    fields = {name: sorted(values) for name, values in collected.items()}
    conflict_fields = [name for name, values in fields.items() if len(values) > 1]
    return fields, conflict_fields


def _confirmation_level(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "")
    text = _text(row)
    confidence = row.get("confidence")
    if row.get("ignored_for_pricing"):
        return "ignored"
    if row.get("is_veto") or category == "veto" or row.get("is_hard_constraint"):
        return "critical"
    if category in CRITICAL_CATEGORIES:
        return "critical"
    topic = _topic(text)
    if topic in {"bid_bond", "deadline", "signature", "copy_count", "qualification", "social_security", "performance", "file_size"}:
        return "critical"
    if row.get("requires_human_confirm") or (confidence is not None and float(confidence) < 0.8):
        return "review"
    if category in ORDINARY_AUTO_ACCEPT_CATEGORIES:
        return "auto_accept"
    if category in REVIEW_CATEGORIES:
        return "review"
    return "auto_accept"


def _lane_for(level: str, category: str, topic: str | None) -> str:
    if level == "ignored":
        return "ignored"
    if level == "auto_accept":
        return "sampling"
    if category in {"project_info", "schedule"} or topic in {"deadline", "bid_bond"}:
        return "project_basics"
    if category == "veto" or topic in {"signature", "copy_count", "file_size"}:
        return "red_lines"
    if category in {"qualification", "performance", "project_team", "personnel"} or topic in {"qualification", "social_security", "performance"}:
        return "qualification_business"
    if category in {"technical", "scoring"} or topic in {"technical", "scoring"}:
        return "technical_response"
    if category in {"format", "business", "special"}:
        return "submission"
    return "technical_response" if level == "review" else "sampling"


def _group_key(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "uncategorized")
    text = _text(row)
    topic = _topic(text)
    if topic:
        return f"{category}:{topic}"
    return f"{category}:{_normalise_for_key(text)}"


def _source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": str(row.get("id")),
        "title": row.get("title"),
        "source_file": row.get("source_file"),
        "source_locator": row.get("source_locator"),
        "source_chunk_id": str(row.get("source_chunk_id")) if row.get("source_chunk_id") else None,
        "text": _text(row),
        "human_confirmed": bool(row.get("human_confirmed")),
    }


def _headline(rows: list[dict[str, Any]]) -> str:
    titles = [str(row.get("title") or "").strip() for row in rows if row.get("title")]
    if titles:
        return Counter(titles).most_common(1)[0][0]
    return _compact(_text(rows[0]))[:80] or "未命名条款包"


def build_requirement_workbench(project_id: str, requirements: list[dict[str, Any]]) -> dict[str, Any]:
    """Return grouped requirement packages for the frontend workbench.

    The grouping is intentionally conservative: it preserves every original
    source and escalates key-field conflicts instead of silently merging them.
    """
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in requirements:
        review_status = str(row.get("review_status") or "pending")
        if review_status in {"merged", "split", "rejected"}:
            continue
        buckets[_group_key(row)].append(row)

    packages: list[dict[str, Any]] = []
    for index, rows in enumerate(buckets.values(), start=1):
        levels = [_confirmation_level(row) for row in rows]
        key_fields, conflict_fields = _merge_key_fields(rows)
        has_conflict = bool(conflict_fields)
        level = "critical" if has_conflict or "critical" in levels else "review" if "review" in levels else levels[0]
        category = Counter(str(row.get("category") or "uncategorized") for row in rows).most_common(1)[0][0]
        topic = _topic(" ".join(_text(row) for row in rows))
        lane = _lane_for(level, category, topic)
        confirmed_count = sum(1 for row in rows if row.get("human_confirmed"))
        confidence_values = [float(row["confidence"]) for row in rows if row.get("confidence") is not None]
        representative = rows[0]
        packages.append(
            {
                "id": f"pkg-{index}",
                "category": category,
                "topic": topic,
                "lane": lane,
                "confirmation_level": level,
                "title": _headline(rows),
                "system_conclusion": _compact(_text(representative))[:280],
                "source_count": len(rows),
                "confirmed_count": confirmed_count,
                "all_confirmed": confirmed_count == len(rows),
                "blocking": level == "critical" and confirmed_count < len(rows),
                "has_conflict": has_conflict,
                "conflict_fields": conflict_fields,
                "key_fields": key_fields,
                "confidence": min(confidence_values) if confidence_values else None,
                "requirements": [str(row.get("id")) for row in rows],
                "sources": [_source(row) for row in rows],
            }
        )

    lane_order = ["project_basics", "red_lines", "qualification_business", "technical_response", "submission", "sampling", "ignored"]
    packages.sort(key=lambda item: (lane_order.index(item["lane"]), item["confirmation_level"] != "critical", item["title"]))

    stats = {
        "total_requirements": len(requirements),
        "package_count": len(packages),
        "critical_count": sum(1 for item in packages if item["confirmation_level"] == "critical"),
        "blocking_count": sum(1 for item in packages if item["blocking"]),
        "conflict_count": sum(1 for item in packages if item["has_conflict"]),
        "auto_accept_count": sum(1 for item in packages if item["confirmation_level"] == "auto_accept"),
        "review_count": sum(1 for item in packages if item["confirmation_level"] == "review"),
        "ignored_count": sum(1 for item in packages if item["confirmation_level"] == "ignored"),
    }

    lanes = [
        {
            "id": lane_id,
            "label": LANE_LABELS[lane_id],
            "packages": [item for item in packages if item["lane"] == lane_id],
        }
        for lane_id in lane_order
    ]
    return {"project_id": str(project_id), "stats": stats, "lanes": lanes, "packages": packages}


__all__ = ["build_requirement_workbench"]
