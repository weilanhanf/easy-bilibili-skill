#!/usr/bin/env python3
"""
补充视频统计数据脚本（用于历史数据升级）

⚠️ 注意：新版本 sync.py 已默认获取完整统计数据，此脚本仅用于：
    1. 升级旧版本同步的视频文档
    2. 更新已有视频的统计数据

用法：
    python scripts/enrich_stats.py           # 补充所有视频
    python scripts/enrich_stats.py --limit 100  # 只补充前100个
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from lib.api import BilibiliAPI, AntiCrawlError, RateLimitError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
VIDEOS_DIR = ROOT_DIR / "knowledge" / "videos"


def load_config() -> Dict[str, Any]:
    """加载配置"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_video_files(limit: Optional[int] = None) -> List[Path]:
    """获取视频文档列表"""
    files = sorted(VIDEOS_DIR.glob("*.md"))
    if limit:
        files = files[:limit]
    return files


def extract_bvid(content: str) -> Optional[str]:
    """从文档内容提取BV号"""
    match = re.search(r"\| BV号 \| (BV\w+) \|", content)
    return match.group(1) if match else None


def update_video_doc(
    content: str,
    stats: Dict[str, Any],
    owner_sign: str = "",
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """更新视频文档，补充统计数据"""
    metadata = metadata or {}

    new_stats = f"""## 统计数据

| 属性 | 值 |
|------|-----|
| 播放量 | {stats.get('view', 0):,} |
| 点赞数 | {stats.get('like', 0):,} |
| 投币数 | {stats.get('coin', 0):,} |
| 收藏数 | {stats.get('fav', 0):,} |
| 分享数 | {stats.get('share', 0):,} |
| 弹幕数 | {stats.get('danmaku', 0):,} |
| 评论数 | {stats.get('reply', 0):,} |
"""

    content = re.sub(
        r"## 统计数据?\n\n\| 属性 \| 值 \|.*?\n\n",
        "",
        content,
        flags=re.DOTALL
    )

    content = re.sub(
        r"(## 观看状态\n\n\| 属性 \| 值 \|.*?\n\n)",
        r"\1" + new_stats + "\n",
        content,
        flags=re.DOTALL
    )

    # 添加UP主简介（如果有）
    if owner_sign and "| UP主简介 |" not in content:
        owner_sign_clean = owner_sign[:100] if len(owner_sign) > 100 else owner_sign
        owner_sign_clean = owner_sign_clean.replace("|", "\\|")
        content = re.sub(
            r"(\| UP主 \| \[.+?\]\(.+?\) \|)\n",
            r"\1\n| UP主简介 | " + owner_sign_clean + " |\n",
            content,
            count=1
        )

    # 添加分区信息（如果有）
    tname = metadata.get("tname", "")
    if tname and "| 分区 |" not in content:
        content = re.sub(
            r"(\| 时长 \| .+ \|)\n",
            r"\1\n| 分区 | " + tname + " |\n",
            content,
            count=1
        )

    return content


def has_full_stats(content: str) -> bool:
    """检查文档是否已有完整统计数据"""
    return "| 点赞数 |" in content


def enrich_single_video(
    api: BilibiliAPI,
    video_file: Path,
    delay: float = 2.0
) -> str:
    """补充单个视频的统计数据

    Returns:
        "success": 更新成功
        "skip": 已有完整数据
        "fail": 处理失败
    """
    content = video_file.read_text(encoding="utf-8")
    bvid = extract_bvid(content)

    if not bvid:
        logger.warning(f"无法提取BV号: {video_file.name}")
        return "fail"

    if has_full_stats(content):
        logger.info(f"已有完整统计: {bvid}")
        return "skip"

    try:
        logger.info(f"获取视频详情: {bvid}")
        detail = api.get_video_detail(bvid)

        stats = detail.get("stat", {})
        owner = detail.get("owner", {})
        owner_sign = owner.get("sign", "") or ""

        metadata = {
            "tname": detail.get("tname_v2") or detail.get("tname") or "",
            "pubdate": detail.get("pubdate", 0),
        }

        new_content = update_video_doc(content, stats, owner_sign, metadata)
        video_file.write_text(new_content, encoding="utf-8")

        logger.info(f"更新成功: {bvid} - 点赞:{stats.get('like',0)} 投币:{stats.get('coin',0)}")
        return "success"

    except AntiCrawlError as e:
        logger.error(f"反爬触发: {e}")
        raise

    except RateLimitError as e:
        logger.error(f"频率限制: {e}")
        raise

    except Exception as e:
        logger.error(f"处理失败: {bvid} - {e}")
        return "fail"


def main(limit: Optional[int] = None):
    """主函数"""
    print("=" * 60)
    print("补充视频统计数据")
    print("=" * 60)

    config = load_config()
    api = BilibiliAPI(config["cookie"])

    video_files = get_video_files(limit)
    total = len(video_files)
    print(f"待处理视频: {total} 个")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, video_file in enumerate(video_files, 1):
        print(f"[{i}/{total}] 处理: {video_file.name}")

        try:
            result = enrich_single_video(api, video_file, delay=2.0)
            if result == "success":
                success_count += 1
            elif result == "skip":
                skip_count += 1
                print(f"    已有完整数据，跳过")
            else:
                fail_count += 1

        except (AntiCrawlError, RateLimitError):
            print("\n触发反爬/限流，暂停处理")
            print(f"已完成: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
            print("建议等待30分钟后重新运行")
            break

    print("\n" + "=" * 60)
    print("处理完成")
    print("=" * 60)
    print(f"成功更新: {success_count}")
    print(f"已有数据: {skip_count}")
    print(f"处理失败: {fail_count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="补充视频统计数据")
    parser.add_argument("--limit", type=int, help="只处理前N个视频")
    args = parser.parse_args()

    main(limit=args.limit)