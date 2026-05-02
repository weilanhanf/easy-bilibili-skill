#!/usr/bin/env python3
"""
B站视频字幕同步脚本（WBI API版本）

用法：
    python scripts/sync_subtitles.py                    # 获取所有视频的字幕URL
    python scripts/sync_subtitles.py --download         # 下载字幕内容
    python scripts/sync_subtitles.py --bvid BV1xxx      # 指定单个视频

功能：
    1. 使用WBI API获取视频字幕URL（需要Cookie）
    2. 获取视频章节/知识点信息（view_points）
    3. 下载字幕内容（可选）
    4. 生成字幕索引文件

数据获取：
    - L0: 视频基本信息（标题、简介、统计数据）- sync.py实现
    - L1: 字幕URL + 章节信息 - 本脚本实现（WBI API）
    - L2: 字幕内容 - 按需获取或--download参数
"""

import argparse
import json
import logging
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lib.api import BilibiliAPI, BilibiliAPIError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 路径配置
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
VIDEOS_DIR = KNOWLEDGE_DIR / "videos"
SUBTITLE_CACHE_DIR = KNOWLEDGE_DIR / "cache" / "subtitles"


# ==================== 配置 ====================

def load_cookie() -> Optional[str]:
    """从config.json加载Cookie"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("cookie")
    except Exception as e:
        logger.warning(f"加载Cookie失败: {e}")
        return None

COOKIE = load_cookie()

# ==================== 数据类 ====================

@dataclass
class SubtitleInfo:
    """字幕信息"""
    bvid: str
    has_subtitle: bool
    languages: List[Dict[str, str]] = field(default_factory=list)
    subtitle_url: Optional[str] = None
    indexed: bool = False
    error: Optional[str] = None
    # 新增：章节/知识点信息
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    aid: Optional[int] = None
    cid: Optional[int] = None


@dataclass
class SubtitleEntry:
    """字幕条目"""
    start_time: float  # 秒
    end_time: float  # 秒
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start_time,
            "end": self.end_time,
            "content": self.content
        }


# ==================== 字幕获取函数 ====================

def get_subtitle_info(bvid: str, use_wbi: bool = True) -> SubtitleInfo:
    """获取视频字幕信息（使用WBI API，需要Cookie）

    Args:
        bvid: 视频BV号
        use_wbi: 是否使用WBI API（默认True，需要Cookie）

    Returns:
        字幕信息对象（包含字幕URL和章节信息）
    """
    # 请求头（模拟浏览器，避免412错误）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 添加Cookie（WBI API需要）
    if COOKIE:
        headers["Cookie"] = COOKIE

    try:
        # 第一步：获取视频详情（获取aid和cid）
        detail_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        req = urllib.request.Request(detail_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            detail_data = json.load(resp)

        if detail_data.get("code") != 0:
            return SubtitleInfo(
                bvid=bvid,
                has_subtitle=False,
                error=f"获取视频详情失败: {detail_data.get('message')}"
            )

        data = detail_data.get("data", {})
        aid = data.get("aid", 0)
        cid = data.get("cid", 0)

        # 第二步：获取字幕列表和章节信息
        if use_wbi and COOKIE:
            # 使用WBI API（需要Cookie，能获取更多字幕）
            wbi_params = {
                "cid": cid,
                "bvid": bvid,
                "aid": aid,
                "isGaiaAvoided": "false",
                "web_location": "1315873",
                "w_rid": "364cdf378b75ef6a0cee77484ce29dbb",  # 硬编码签名（来自Bilibili-MCP）
                "wts": int(time.time()),
            }
            player_url = "https://api.bilibili.com/x/player/wbi/v2?" + "&".join([f"{k}={v}" for k, v in wbi_params.items()])
        else:
            # 使用普通API（不需要Cookie，但字幕覆盖率低）
            player_url = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"

        req = urllib.request.Request(player_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            player_data = json.load(resp)

        if player_data.get("code") != 0:
            return SubtitleInfo(
                bvid=bvid,
                has_subtitle=False,
                error=f"获取播放器信息失败: {player_data.get('message')}"
            )

        player_info = player_data.get("data", {})

        # 提取字幕信息
        subtitle_data = player_info.get("subtitle", {})
        subtitles = subtitle_data.get("subtitles", [])

        # 提取章节/知识点信息
        view_points = player_info.get("view_points", [])
        chapters = []
        for vp in view_points:
            chapters.append({
                "from": vp.get("from", 0),
                "to": vp.get("to", 0),
                "content": vp.get("content", ""),
                "img_url": vp.get("imgUrl", ""),
            })

        if not subtitles:
            return SubtitleInfo(
                bvid=bvid,
                has_subtitle=False,
                chapters=chapters,
                aid=aid,
                cid=cid
            )

        # 提取字幕URL
        languages = []
        primary_url = None

        for sub in subtitles:
            lang_info = {
                "lang": sub.get("lan", ""),
                "lang_doc": sub.get("lan_doc", ""),
                "url": sub.get("subtitle_url", "")
            }
            languages.append(lang_info)

            # 优先选择中文字幕
            if "中文" in sub.get("lan_doc", "") or sub.get("lan", "") == "ai-zh":
                primary_url = sub.get("subtitle_url", "")

        # 如果没有中文字幕，选择第一个
        if not primary_url and languages:
            primary_url = languages[0].get("url", "")

        return SubtitleInfo(
            bvid=bvid,
            has_subtitle=True,
            languages=languages,
            subtitle_url=primary_url,
            chapters=chapters,
            aid=aid,
            cid=cid
        )

    except Exception as e:
        return SubtitleInfo(
            bvid=bvid,
            has_subtitle=False,
            error=str(e)
        )


def download_subtitle_content(subtitle_url: str) -> Optional[List[SubtitleEntry]]:
    """下载字幕内容

    Args:
        subtitle_url: 字幕URL

    Returns:
        字幕条目列表
    """
    # 请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }

    try:
        # 处理URL格式
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url

        req = urllib.request.Request(subtitle_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            subtitle_data = json.load(resp)

        body = subtitle_data.get("body", [])
        entries = []

        for item in body:
            entry = SubtitleEntry(
                start_time=item.get("from", 0),
                end_time=item.get("to", 0),
                content=item.get("content", "")
            )
            entries.append(entry)

        return entries

    except Exception as e:
        logger.error(f"下载字幕失败: {e}")
        return None


def generate_subtitle_index(entries: List[SubtitleEntry], max_entries: int = 100) -> str:
    """生成字幕索引（压缩版，用于检索）

    Args:
        entries: 字幕条目列表
        max_entries: 最大条目数

    Returns:
        索引文本
    """
    if not entries:
        return ""

    # 采样策略：均匀采样
    total = len(entries)
    if total <= max_entries:
        sampled = entries
    else:
        step = total // max_entries
        sampled = entries[::step][:max_entries]

    lines = []
    for entry in sampled:
        minutes = int(entry.start_time // 60)
        seconds = int(entry.start_time % 60)
        time_str = f"[{minutes:02d}:{seconds:02d}]"
        lines.append(f"{time_str} {entry.content}")

    return "\n".join(lines)


# ==================== 缓存管理 ====================

def save_subtitle_cache(bvid: str, info: SubtitleInfo, entries: Optional[List[SubtitleEntry]] = None, subtitle_lang: str = "") -> None:
    """保存字幕缓存

    Args:
        bvid: 视频BV号
        info: 字幕信息
        entries: 字幕条目（可选）
        subtitle_lang: 实际下载的字幕语言（如 "中文"、"English"）
    """
    SUBTITLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 确定字幕语言
    if not subtitle_lang and info.subtitle_url:
        for lang in info.languages:
            if lang.get("url") == info.subtitle_url:
                subtitle_lang = lang.get("lang_doc", "")
                break

    cache_data = {
        "bvid": bvid,
        "aid": info.aid,
        "cid": info.cid,
        "has_subtitle": info.has_subtitle,
        "languages": info.languages,
        "subtitle_url": info.subtitle_url,
        "subtitle_lang": subtitle_lang,
        "chapters": info.chapters,
        "indexed": entries is not None,
        "updated_at": datetime.now().isoformat()
    }

    if entries:
        cache_data["entries"] = [e.to_dict() for e in entries]
        cache_data["index_text"] = generate_subtitle_index(entries)

    cache_file = SUBTITLE_CACHE_DIR / f"{bvid}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def load_subtitle_cache(bvid: str) -> Optional[Dict[str, Any]]:
    """加载字幕缓存

    Args:
        bvid: 视频BV号

    Returns:
        缓存数据
    """
    cache_file = SUBTITLE_CACHE_DIR / f"{bvid}.json"
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载缓存失败: {e}")
        return None


# ==================== 同步函数 ====================

def sync_subtitle_urls(bvids: List[str], delay: float = 0.5) -> Dict[str, SubtitleInfo]:
    """同步视频字幕URL和章节信息

    Args:
        bvids: 视频BV号列表
        delay: 请求延迟

    Returns:
        BV号到字幕信息的映射
    """
    results = {}
    total = len(bvids)

    print(f"\n[1/2] 获取字幕和章节信息...")
    print(f"   视频总数: {total}")
    if COOKIE:
        print(f"   Cookie状态: 已加载")
    else:
        print(f"   Cookie状态: 未加载（字幕覆盖率可能较低）")

    subtitle_count = 0
    chapter_count = 0

    for i, bvid in enumerate(bvids):
        # 检查缓存
        cache = load_subtitle_cache(bvid)
        if cache:
            info = SubtitleInfo(
                bvid=bvid,
                has_subtitle=cache.get("has_subtitle", False),
                languages=cache.get("languages", []),
                subtitle_url=cache.get("subtitle_url"),
                indexed=cache.get("indexed", False),
                chapters=cache.get("chapters", []),
                aid=cache.get("aid"),
                cid=cache.get("cid")
            )
            results[bvid] = info

            if info.has_subtitle:
                subtitle_count += 1
            if info.chapters:
                chapter_count += 1

            if (i + 1) % 100 == 0:
                print(f"   进度: {i + 1}/{total} (缓存命中)")
            continue

        # 获取字幕信息
        info = get_subtitle_info(bvid)
        results[bvid] = info

        # 保存缓存
        save_subtitle_cache(bvid, info)

        if info.has_subtitle:
            subtitle_count += 1
        if info.chapters:
            chapter_count += 1

        # 进度显示
        if (i + 1) % 50 == 0:
            print(f"   进度: {i + 1}/{total}")

        # 延迟
        time.sleep(delay)

    print(f"\n[2/2] 统计结果...")
    print(f"   有字幕: {subtitle_count} 个 ({subtitle_count * 100 // max(total, 1)}%)")
    print(f"   有章节: {chapter_count} 个 ({chapter_count * 100 // max(total, 1)}%)")
    print(f"   无字幕: {total - subtitle_count} 个")

    return results


def download_subtitles(bvids: List[str], delay: float = 1.0, batch_size: int = 100) -> None:
    """下载字幕内容

    Args:
        bvids: 视频BV号列表
        delay: 请求延迟
        batch_size: 批次大小
    """
    total = len(bvids)
    downloaded = 0
    failed = 0

    print(f"\n下载字幕内容...")
    print(f"   目标视频: {total} 个")
    print(f"   批次大小: {batch_size}")

    for i, bvid in enumerate(bvids):
        # 检查缓存
        cache = load_subtitle_cache(bvid)
        if cache and cache.get("indexed"):
            downloaded += 1
            continue

        # 获取字幕信息
        if not cache:
            info = get_subtitle_info(bvid)
            save_subtitle_cache(bvid, info)
        else:
            info = SubtitleInfo(
                bvid=bvid,
                has_subtitle=cache.get("has_subtitle", False),
                subtitle_url=cache.get("subtitle_url")
            )

        # 下载字幕
        if info.has_subtitle and info.subtitle_url:
            entries = download_subtitle_content(info.subtitle_url)
            if entries:
                save_subtitle_cache(bvid, info, entries)
                downloaded += 1
            else:
                failed += 1
        else:
            failed += 1

        # 进度显示
        if (i + 1) % 20 == 0:
            print(f"   进度: {i + 1}/{total} (成功: {downloaded}, 失败: {failed})")

        # 延迟
        time.sleep(delay)

    print(f"\n下载完成:")
    print(f"   成功: {downloaded}")
    print(f"   失败: {failed}")


# ==================== 主函数 ====================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="B站视频字幕同步")
    parser.add_argument("--download", action="store_true", help="下载字幕内容")
    parser.add_argument("--bvid", type=str, help="指定单个视频BV号")
    parser.add_argument("--batch", type=int, default=100, help="批次大小")
    args = parser.parse_args()

    print("=" * 50)
    print("B站视频字幕同步")
    print("=" * 50)

    # 获取视频列表
    if args.bvid:
        bvids = [args.bvid]
    else:
        # 从现有视频文档中获取BV号
        bvids = []
        for f in VIDEOS_DIR.glob("*.md"):
            bvids.append(f.stem)

        if not bvids:
            print("[ERROR] 未找到视频文档，请先运行 python scripts/sync.py")
            sys.exit(1)

    print(f"视频数量: {len(bvids)}")

    # 同步字幕URL
    results = sync_subtitle_urls(bvids)

    # 下载字幕内容
    if args.download:
        subtitle_bvids = [bvid for bvid, info in results.items() if info.has_subtitle]
        print(f"\n需要下载字幕的视频: {len(subtitle_bvids)} 个")
        download_subtitles(subtitle_bvids, batch_size=args.batch)

    print("\n[OK] 字幕同步完成！")
    print(f"缓存目录: {SUBTITLE_CACHE_DIR}")


if __name__ == "__main__":
    main()
