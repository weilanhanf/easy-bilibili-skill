#!/usr/bin/env python3
"""
B站视频信息增强脚本

用法：
    python scripts/enrich_video_info.py                    # 增强所有视频信息
    python scripts/enrich_video_info.py --bvid BV1xxx      # 指定单个视频
    python scripts/enrich_video_info.py --limit 100       # 限制处理数量

功能：
    整合所有可获取的视频信息，更新MD文档：
    - 基本信息（BV号、aid、cid、UP主、分区、时长、发布时间等）
    - 视频简介（完整内容）
    - 动态描述
    - 章节/知识点（带时间点和截图）
    - 字幕信息（语言、URL、状态）
    - 观看状态（进度、最近观看）
    - 统计数据（播放、收藏、点赞、投币等）

数据来源：
    - 视频详情API: /x/web-interface/view
    - WBI播放器API: /x/player/wbi/v2（字幕+章节）
    - 本地缓存: knowledge/cache/subtitles/{bvid}.json
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 路径配置
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
VIDEOS_DIR = KNOWLEDGE_DIR / "videos"
SUBTITLE_CACHE_DIR = KNOWLEDGE_DIR / "cache" / "subtitles"


# ==================== 配置加载 ====================

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

# 分区映射表（一级分区）
TID_MAP = {
    1: "游戏",
    13: "番剧",
    23: "国创",
    11: "电视剧",
    177: "纪录片",
    223: "综艺",
    167: "国创",
    160: "生活",
    138: "搞笑",
    250: "美食圈",
    251: "动物圈",
    239: "健身圈",
    217: "潮流圈",
    76: "音乐",
    75: "动物圈",
    74: "游戏",
    211: "美食",
    208: "汽车",
    207: "数码",
    205: "时尚",
    206: "资讯",
    36: "知识",
    188: "科技",
    189: "科学",
    190: "人文历史",
    192: "财经",
    201: "校园学习",
    202: "职业职场",
    203: "设计",
}


# ==================== 数据获取 ====================

def get_video_detail(bvid: str, retry_count: int = 0) -> Tuple[Optional[Dict[str, Any]], bool]:
    """获取视频详细信息

    Args:
        bvid: 视频BV号
        retry_count: 重试次数

    Returns:
        (视频详情数据, 是否触发限流)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if COOKIE:
        headers["Cookie"] = COOKIE

    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)

        if data.get("code") != 0:
            msg = data.get("message", "")
            code = data.get("code")
            # 视频已删除或不存在，不算失败
            if code in [62002, -404]:  # 稿件已删除/不存在
                logger.info(f"视频已删除或不存在: {bvid}")
                return None, False
            if "请求过于频繁" in msg or code == 412:
                logger.warning(f"触发限流: {bvid}")
                return None, True
            logger.error(f"获取视频详情失败({code}): {msg}")
            return None, False

        return data.get("data", {}), False

    except urllib.error.HTTPError as e:
        if e.code == 412:
            logger.warning(f"触发反爬限制(412): {bvid}")
            return None, True
        logger.error(f"HTTP错误: {e}")
        return None, False
    except Exception as e:
        logger.error(f"获取视频详情异常: {e}")
        return None, False


def get_player_info(bvid: str, aid: int, cid: int) -> Optional[Dict[str, Any]]:
    """获取播放器信息（字幕+章节）

    Args:
        bvid: 视频BV号
        aid: 视频aid
        cid: 视频cid

    Returns:
        播放器信息数据
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
    }
    if COOKIE:
        headers["Cookie"] = COOKIE

    try:
        # 使用WBI API（需要Cookie）
        wbi_params = {
            "cid": cid,
            "bvid": bvid,
            "aid": aid,
            "isGaiaAvoided": "false",
            "web_location": "1315873",
            "w_rid": "364cdf378b75ef6a0cee77484ce29dbb",
            "wts": int(time.time()),
        }
        url = "https://api.bilibili.com/x/player/wbi/v2?" + "&".join([f"{k}={v}" for k, v in wbi_params.items()])

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)

        if data.get("code") != 0:
            logger.warning(f"获取播放器信息失败: {data.get('message')}")
            return None

        return data.get("data", {})

    except Exception as e:
        logger.warning(f"获取播放器信息异常: {e}")
        return None


def load_subtitle_cache(bvid: str) -> Optional[Dict[str, Any]]:
    """加载字幕缓存"""
    cache_file = SUBTITLE_CACHE_DIR / f"{bvid}.json"
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载字幕缓存失败: {e}")
        return None


def save_subtitle_cache(bvid: str, data: Dict[str, Any]) -> None:
    """保存字幕缓存"""
    SUBTITLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = SUBTITLE_CACHE_DIR / f"{bvid}.json"

    # 合并现有缓存
    existing = load_subtitle_cache(bvid) or {}
    existing.update(data)
    existing["updated_at"] = datetime.now().isoformat()

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ==================== MD文档生成 ====================

def format_duration(seconds: int) -> str:
    """格式化时长"""
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}小时{minutes}分钟"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes}分钟"
    else:
        return f"{seconds}秒"


def format_timestamp(timestamp: int) -> str:
    """格式化时间戳"""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return str(timestamp)


def format_time_range(from_sec: float, to_sec: float) -> str:
    """格式化时间范围"""
    from_mins = int(from_sec // 60)
    from_secs = int(from_sec % 60)
    to_mins = int(to_sec // 60)
    to_secs = int(to_sec % 60)
    return f"[{from_mins:02d}:{from_secs:02d}-{to_mins:02d}:{to_secs:02d}]"


def generate_video_md(bvid: str, video_data: Dict, player_data: Optional[Dict],
                      cache_data: Optional[Dict], existing_md: Optional[str] = None) -> str:
    """生成视频MD文档

    Args:
        bvid: 视频BV号
        video_data: 视频详情数据
        player_data: 播放器数据
        cache_data: 字幕缓存数据
        existing_md: 现有MD内容（用于保留观看状态）

    Returns:
        MD文档内容
    """
    lines = []

    # 标题
    title = video_data.get("title", "未知标题")
    lines.append(f"# {title}")
    lines.append("")

    # 基本信息
    lines.append("## 基本信息")
    lines.append("")
    lines.append("| 属性 | 值 |")
    lines.append("|------|-----|")

    # BV号
    lines.append(f"| BV号 | {bvid} |")

    # aid和cid
    aid = video_data.get("aid", 0)
    cid = video_data.get("cid", 0)
    lines.append(f"| aid | {aid} |")
    lines.append(f"| cid | {cid} |")

    # UP主
    owner = video_data.get("owner", {})
    owner_name = owner.get("name", "未知")
    owner_mid = owner.get("mid", 0)
    lines.append(f"| UP主 | [{owner_name}](https://space.bilibili.com/{owner_mid}) |")

    # 分区
    tname = video_data.get("tname", "")
    tid = video_data.get("tid", 0)
    parent_tname = TID_MAP.get(tid, "")
    if parent_tname and tname:
        partition = f"{parent_tname} → {tname}"
    elif tname:
        partition = tname
    elif parent_tname:
        partition = parent_tname
    else:
        partition = "未知"
    lines.append(f"| 分区 | {partition} |")

    # 时长
    duration = video_data.get("duration", 0)
    lines.append(f"| 时长 | {format_duration(duration)} ({duration}秒) |")

    # 发布时间
    pubdate = video_data.get("pubdate", 0)
    if pubdate:
        lines.append(f"| 发布时间 | {format_timestamp(pubdate)} |")

    # 收藏时间（从现有MD提取）
    fav_time = ""
    fav_folder = "默认收藏夹"
    if existing_md:
        fav_match = re.search(r"\| 收藏时间 \| ([^|]+) \|", existing_md)
        if fav_match:
            fav_time = fav_match.group(1).strip()
        folder_match = re.search(r"\| 收藏夹 \| ([^|]+) \|", existing_md)
        if folder_match:
            fav_folder = folder_match.group(1).strip()
    if fav_time:
        lines.append(f"| 收藏时间 | {fav_time} |")
    lines.append(f"| 收藏夹 | {fav_folder} |")

    # 原创状态
    copyright_type = video_data.get("copyright", 1)
    if copyright_type == 1:
        copyright_str = "原创"
    else:
        source = video_data.get("source", "")
        copyright_str = f"转载自：{source}" if source else "转载"
    lines.append(f"| 原创状态 | {copyright_str} |")

    # 封面
    pic = video_data.get("pic", "")
    if pic:
        lines.append(f"| 封面 | [查看封面]({pic}) |")

    # 视频链接
    lines.append(f"| 链接 | [观看视频](https://www.bilibili.com/video/{bvid}) |")

    lines.append("")

    # 简介
    lines.append("## 简介")
    lines.append("")
    desc = video_data.get("desc", "")
    if desc:
        # 解析简介中的链接
        desc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[\1](\2)", desc)
        lines.append(desc)
    else:
        lines.append("无简介")
    lines.append("")

    # 动态（如有）
    dynamic = video_data.get("dynamic", "")
    if dynamic:
        lines.append("## 动态")
        lines.append("")
        lines.append(dynamic)
        lines.append("")

    # 章节/知识点
    chapters = cache_data.get("chapters", []) if cache_data else []
    if player_data and not chapters:
        view_points = player_data.get("view_points", [])
        chapters = [
            {
                "from": vp.get("from", 0),
                "to": vp.get("to", 0),
                "content": vp.get("content", ""),
                "img_url": vp.get("imgUrl", ""),
            }
            for vp in view_points
        ]

    if chapters:
        lines.append("## 章节/知识点")
        lines.append("")
        lines.append("| 时间段 | 内容 |")
        lines.append("|--------|------|")
        for ch in chapters:
            time_range = format_time_range(ch.get("from", 0), ch.get("to", 0))
            content = ch.get("content", "")
            lines.append(f"| {time_range} | {content} |")
        lines.append("")

    # 分P信息
    pages = video_data.get("pages", [])
    if len(pages) > 1:
        lines.append("## 分P信息")
        lines.append("")
        lines.append("| P序号 | 标题 | 时长 |")
        lines.append("|-------|------|------|")
        for i, page in enumerate(pages, 1):
            page_title = page.get("part", f"第{i}部分")
            page_duration = page.get("duration", 0)
            lines.append(f"| P{i} | {page_title} | {format_duration(page_duration)} |")
        lines.append("")

    # 字幕信息
    subtitle_info = cache_data if cache_data else {}
    if player_data and not subtitle_info.get("has_subtitle"):
        subtitle_data = player_data.get("subtitle", {})
        subtitles = subtitle_data.get("subtitles", [])
        subtitle_info = {
            "has_subtitle": bool(subtitles),
            "languages": [
                {"lang": s.get("lan", ""), "lang_doc": s.get("lan_doc", ""), "url": s.get("subtitle_url", "")}
                for s in subtitles
            ]
        }

    lines.append("## 字幕信息")
    lines.append("")
    lines.append("| 属性 | 值 |")
    lines.append("|------|-----|")

    has_sub = subtitle_info.get("has_subtitle", False)
    if has_sub:
        lines.append("| 字幕状态 | 有字幕 |")
        languages = subtitle_info.get("languages", [])
        if languages:
            lang_names = [lang.get("lang_doc", "") for lang in languages]
            lines.append(f"| 语言 | {', '.join(lang_names)} |")

        # 字幕摘要（如果已下载）
        if cache_data and cache_data.get("index_text"):
            index_text = cache_data.get("index_text", "")
            # 取前500字符作为摘要
            if len(index_text) > 500:
                index_text = index_text[:500] + "..."
            lines.append("| 字幕摘要 | (见下方) |")
            lines.append("")
            lines.append("### 字幕内容摘要")
            lines.append("")
            lines.append("```")
            lines.append(index_text)
            lines.append("```")
    else:
        lines.append("| 字幕状态 | 无字幕 |")

    lines.append("")

    # 合作信息
    staff = video_data.get("staff", [])
    if staff:
        lines.append("## 合作信息")
        lines.append("")
        lines.append("| UP主 | 角色 |")
        lines.append("|------|------|")
        for s in staff:
            name = s.get("name", "")
            title = s.get("title", "")
            lines.append(f"| {name} | {title} |")
        lines.append("")

    # 观看状态（从现有MD提取）
    if existing_md:
        watch_match = re.search(r"## 观看状态\n\n.*?(?=\n## |\Z)", existing_md, re.DOTALL)
        if watch_match:
            lines.append("## 观看状态")
            lines.append("")
            lines.append(watch_match.group(0).replace("## 观看状态\n\n", ""))
            lines.append("")

    # 统计数据
    lines.append("## 统计数据")
    lines.append("")
    lines.append("| 属性 | 值 |")
    lines.append("|------|-----|")

    stat = video_data.get("stat", {})
    if stat:
        lines.append(f"| 播放量 | {stat.get('view', 0):,} |")
        lines.append(f"| 收藏数 | {stat.get('favorite', 0):,} |")
        lines.append(f"| 点赞数 | {stat.get('like', 0):,} |")
        lines.append(f"| 投币数 | {stat.get('coin', 0):,} |")
        lines.append(f"| 分享数 | {stat.get('share', 0):,} |")
        lines.append(f"| 弹幕数 | {stat.get('danmaku', 0):,} |")
        lines.append(f"| 评论数 | {stat.get('reply', 0):,} |")

    lines.append("")

    return "\n".join(lines)


# ==================== 主逻辑 ====================

def enrich_video(bvid: str) -> Tuple[bool, bool]:
    """增强单个视频的信息

    Args:
        bvid: 视频BV号

    Returns:
        (是否成功, 是否触发限流)
    """
    # 读取现有MD文档
    md_file = VIDEOS_DIR / f"{bvid}.md"
    existing_md = None
    if md_file.exists():
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                existing_md = f.read()
        except Exception as e:
            logger.warning(f"读取现有MD失败: {e}")

    # 获取视频详情
    video_data, rate_limited = get_video_detail(bvid)
    if rate_limited:
        return False, True
    if not video_data:
        logger.error(f"获取视频详情失败: {bvid}")
        return False, False

    aid = video_data.get("aid", 0)
    cid = video_data.get("cid", 0)

    # 获取播放器信息（字幕+章节）- 简化处理，失败不影响
    player_data = get_player_info(bvid, aid, cid)

    # 加载字幕缓存
    cache_data = load_subtitle_cache(bvid)

    # 如果缓存过时，更新缓存
    if player_data:
        cache_update = {
            "bvid": bvid,
            "aid": aid,
            "cid": cid,
            "has_subtitle": bool(player_data.get("subtitle", {}).get("subtitles", [])),
            "languages": [
                {"lang": s.get("lan", ""), "lang_doc": s.get("lan_doc", ""), "url": s.get("subtitle_url", "")}
                for s in player_data.get("subtitle", {}).get("subtitles", [])
            ],
            "chapters": [
                {"from": vp.get("from", 0), "to": vp.get("to", 0), "content": vp.get("content", ""), "img_url": vp.get("imgUrl", "")}
                for vp in player_data.get("view_points", [])
            ]
        }
        save_subtitle_cache(bvid, cache_update)
        cache_data = load_subtitle_cache(bvid)

    # 生成新MD文档
    new_md = generate_video_md(bvid, video_data, player_data, cache_data, existing_md)

    # 保存MD文档
    try:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(new_md)
        return True, False
    except Exception as e:
        logger.error(f"保存MD文档失败: {e}")
        return False, False


def enrich_all_videos(limit: int = 0) -> None:
    """增强所有视频信息

    Args:
        limit: 限制处理数量（0表示不限制）
    """
    # 获取所有视频BV号
    bvids = []
    for f in VIDEOS_DIR.glob("*.md"):
        bvids.append(f.stem)

    if not bvids:
        logger.error("未找到视频文档")
        return

    total = len(bvids)
    if limit > 0:
        bvids = bvids[:limit]
        total = limit

    print(f"\n{'=' * 50}", flush=True)
    print("B站视频信息增强", flush=True)
    print(f"{'=' * 50}", flush=True)
    print(f"视频总数: {total}", flush=True)
    if COOKIE:
        print("Cookie状态: 已加载", flush=True)
    else:
        print("Cookie状态: 未加载", flush=True)

    success = 0
    failed = 0
    rate_limit_hits = 0
    start_time = time.time()
    consecutive_rate_limits = 0  # 连续限流计数

    for i, bvid in enumerate(bvids):
        success_flag, rate_limited = enrich_video(bvid)
        if success_flag:
            success += 1
            consecutive_rate_limits = 0
        else:
            failed += 1
        if rate_limited:
            rate_limit_hits += 1
            consecutive_rate_limits += 1
            if consecutive_rate_limits >= 3:
                print(f"\n连续限流{consecutive_rate_limits}次，暂停60秒...", flush=True)
                time.sleep(60)
                consecutive_rate_limits = 0
            else:
                time.sleep(5)

        # 进度条显示
        elapsed = time.time() - start_time
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        eta = (total - i - 1) / rate if rate > 0 else 0
        percent = (i + 1) / total * 100
        bar_len = 30
        filled = int(bar_len * (i + 1) / total)
        bar = '#' * filled + '-' * (bar_len - filled)
        print(f"\r[{bar}] {i+1}/{total} ({percent:.1f}%) | OK:{success} FAIL:{failed} | ETA:{int(eta)}s", end='', flush=True)

        time.sleep(0.05)

    print(flush=True)  # 完成后换行

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}", flush=True)
    print(f"增强完成", flush=True)
    print(f"成功: {success}", flush=True)
    print(f"失败: {failed}", flush=True)
    print(f"限流次数: {rate_limit_hits}", flush=True)
    print(f"总耗时: {int(elapsed)}秒 ({int(elapsed//60)}分{int(elapsed%60)}秒)", flush=True)
    print(f"{'=' * 50}", flush=True)

    # 更新进度文件
    update_sync_progress(total, success, failed, rate_limit_hits, "completed")


def update_sync_progress(total: int, success: int, failed: int, rate_limits: int, status: str) -> None:
    """更新同步进度文件"""
    progress_file = KNOWLEDGE_DIR / "sync_progress.json"

    try:
        if progress_file.exists():
            with open(progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
        else:
            progress = {}

        progress["video_info_enrich"] = {
            "total": total,
            "completed": success,
            "success": success,
            "failed": failed,
            "rate_limits": rate_limits,
            "percentage": f"{success * 100 / total:.1f}%" if total > 0 else "0%",
            "status": status,
            "updated_at": datetime.now().isoformat()
        }

        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"更新进度文件失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="B站视频信息增强")
    parser.add_argument("--bvid", type=str, help="指定单个视频BV号")
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量")
    args = parser.parse_args()

    if args.bvid:
        print(f"\n{'=' * 50}", flush=True)
        print("B站视频信息增强", flush=True)
        print(f"{'=' * 50}", flush=True)
        print(f"目标视频: {args.bvid}", flush=True)
        success_flag, _ = enrich_video(args.bvid)
        if success_flag:
            print("\n成功！", flush=True)
        else:
            print("\n失败！", flush=True)
    else:
        enrich_all_videos(args.limit)


if __name__ == "__main__":
    main()
