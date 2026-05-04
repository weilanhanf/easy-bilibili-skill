"""
B站 API 封装模块

提供 B站 API 的封装，包括：
- 视频信息获取
- 收藏夹管理
- 观看历史
- UP主信息
"""

from .api import BilibiliAPI, VideoInfo, WatchProgress, UpInfo

__all__ = ["BilibiliAPI", "VideoInfo", "WatchProgress", "UpInfo"]
