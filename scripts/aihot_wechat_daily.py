"""Send the AIHot daily digest via Server酱 to personal WeChat.

The script intentionally uses only the Python standard library so it can run
from GitHub Actions without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_DAILY_URL = "https://aihot.virxact.com/api/public/daily"
DEFAULT_MAX_CHARS = 3800
DEFAULT_MAX_ITEMS_PER_SECTION = 8


class AIHotWechatError(RuntimeError):
    """Raised when fetching or sending the digest fails."""


@dataclass(frozen=True)
class Config:
    daily_url: str
    sendkey: str | None
    date: str | None
    dry_run: bool
    max_chars: int
    max_items_per_section: int


def parse_args(argv: list[str]) -> Config:
    parser = argparse.ArgumentParser(
        description="Fetch AIHot daily digest and send it via Server酱 to personal WeChat."
    )
    parser.add_argument(
        "--daily-url",
        default=os.environ.get("AIHOT_DAILY_URL", DEFAULT_DAILY_URL),
        help=f"AIHot daily API URL. Default: {DEFAULT_DAILY_URL}",
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("AIHOT_DATE"),
        help="Optional date in YYYY-MM-DD. Uses /daily/<date> when provided.",
    )
    parser.add_argument(
        "--sendkey",
        default=os.environ.get("SENDKEY"),
        help="Server酱 SendKey. Can also be set via SENDKEY env var.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"},
        help="Print the generated markdown instead of sending it.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=int(os.environ.get("WECHAT_MAX_CHARS", DEFAULT_MAX_CHARS)),
        help=f"Maximum characters per WeCom markdown message. Default: {DEFAULT_MAX_CHARS}",
    )
    parser.add_argument(
        "--max-items-per-section",
        type=int,
        default=int(
            os.environ.get("AIHOT_MAX_ITEMS_PER_SECTION", DEFAULT_MAX_ITEMS_PER_SECTION)
        ),
        help=(
            "Maximum items kept in each section to avoid overly long group messages. "
            f"Default: {DEFAULT_MAX_ITEMS_PER_SECTION}"
        ),
    )
    args = parser.parse_args(argv)

    if args.max_chars < 500:
        parser.error("--max-chars must be at least 500")
    if args.max_items_per_section < 1:
        parser.error("--max-items-per-section must be at least 1")
    if not args.dry_run and not args.sendkey:
        parser.error("SENDKEY is required unless --dry-run is used")

    return Config(
        daily_url=args.daily_url,
        sendkey=args.sendkey,
        date=args.date,
        dry_run=args.dry_run,
        max_chars=args.max_chars,
        max_items_per_section=args.max_items_per_section,
    )


def daily_url_with_date(base_url: str, date: str | None) -> str:
    if not date:
        return base_url

    parsed = urllib.parse.urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/daily"):
        path = f"{path}/{urllib.parse.quote(date)}"
    else:
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("date", date))
        return urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(query))
        )
    return urllib.parse.urlunparse(parsed._replace(path=path))


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 25,
) -> Any:
    body = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "aihot-wechat-daily/1.0",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AIHotWechatError(f"HTTP {exc.code} from {url}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise AIHotWechatError(f"Failed to reach {url}: {exc.reason}") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:500].decode("utf-8", errors="replace")
        raise AIHotWechatError(f"Invalid JSON from {url}: {preview}") from exc


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def trim_summary(summary: str, limit: int = 260) -> str:
    if len(summary) <= limit:
        return summary
    return summary[: limit - 1].rstrip() + "…"


def item_to_markdown(index: int, item: dict[str, Any]) -> str:
    title = clean_text(item.get("title")) or "无标题"
    summary = trim_summary(clean_text(item.get("summary")))
    source_url = clean_text(item.get("sourceUrl") or item.get("url"))
    source_name = clean_text(item.get("sourceName")) or "原文"

    lines = [f"{index}. **{title}**"]
    if summary:
        lines.append(summary)
    if source_url:
        lines.append(f"[{source_name}]({source_url})")
    elif source_name:
        lines.append(f"来源：{source_name}")
    return "\n".join(lines)


def build_section_blocks(data: dict[str, Any], max_items_per_section: int) -> list[str]:
    blocks: list[str] = []
    date = clean_text(data.get("date")) or "今日"
    generated_at = clean_text(data.get("generatedAt"))

    title_lines = [f"**AIHot 每日精选 | {date}**"]
    if generated_at:
        title_lines.append(f"> 生成时间：{generated_at}")
    lead = clean_text(data.get("lead"))
    if lead:
        title_lines.append(f"> {lead}")
    blocks.append("\n".join(title_lines))

    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = clean_text(section.get("label")) or "未分类"
        items = [item for item in section.get("items") or [] if isinstance(item, dict)]
        if not items:
            continue

        lines = [f"**【{label}】**"]
        for index, item in enumerate(items[:max_items_per_section], 1):
            lines.append(item_to_markdown(index, item))
        if len(items) > max_items_per_section:
            lines.append(f"_本组还有 {len(items) - max_items_per_section} 条，已省略。_")
        blocks.append("\n\n".join(lines))

    flashes = [flash for flash in data.get("flashes") or [] if isinstance(flash, dict)]
    if flashes:
        lines = ["**【快讯】**"]
        for index, flash in enumerate(flashes[:max_items_per_section], 1):
            lines.append(item_to_markdown(index, flash))
        blocks.append("\n\n".join(lines))

    if len(blocks) == 1:
        blocks.append("_今天接口没有返回可推送条目。_")
    return blocks


def split_messages(blocks: list[str], max_chars: int) -> list[str]:
    messages: list[str] = []
    current = ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if len(block) > max_chars:
            wrapped = textwrap.wrap(
                block,
                width=max_chars,
                break_long_words=False,
                break_on_hyphens=False,
            )
            for part in wrapped:
                if current:
                    messages.append(current)
                    current = ""
                messages.append(part)
            continue

        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                messages.append(current)
            current = block

    if current:
        messages.append(current)
    return messages


def send_serverchan(sendkey: str, title: str, content: str) -> dict[str, Any]:
    result = http_json(
        f"https://sctapi.ftqq.com/{sendkey}.send",
        method="POST",
        payload={"title": title, "desp": content},
    )
    # ponytail: Server酱 returns json or plain text depending on sendkey; be lenient
    if isinstance(result, dict) and result.get("code") == 0:
        return result
    if isinstance(result, str) and "success" in result.lower():
        return {"raw": result}  # type: ignore[return-value]
    raise AIHotWechatError(f"Server酱 rejected message: {result!r}")


def run(config: Config) -> int:
    url = daily_url_with_date(config.daily_url, config.date)
    data = http_json(url)
    if not isinstance(data, dict):
        raise AIHotWechatError(f"Unexpected AIHot response shape: {type(data).__name__}")

    blocks = build_section_blocks(data, config.max_items_per_section)
    messages = split_messages(blocks, config.max_chars)
    if config.dry_run:
        for index, message in enumerate(messages, 1):
            print(f"----- message {index}/{len(messages)} -----")
            print(message)
            print()
        return 0

    date = clean_text(data.get("date")) or "AIHot"
    for i, message in enumerate(messages):
        send_serverchan(config.sendkey, f"AIHot 每日精选 {date} ({i + 1}/{len(messages)})", message)
    print(f"Sent {len(messages)} Server酱 message(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        config = parse_args(sys.argv[1:] if argv is None else argv)
        return run(config)
    except AIHotWechatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
