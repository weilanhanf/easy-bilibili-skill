"""
B站 API 封装

提供 B站 API 的统一封装，支持：
- Cookie 验证
- 收藏夹管理
- 观看历史
- UP主信息获取
- 视频详情查询

使用示例：
    from lib.api import BilibiliAPI

    api = BilibiliAPI(cookie_str)
    result = api.validate_cookie()
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

# 配置日志
logger = logging.getLogger(__name__)



@dataclass
class VideoInfo:
    """视频信息数据类"""
    bvid: str
    title: str
    intro: str
    duration: int  # 秒
    author: str
    author_id: int
    cover: str
    fav_time: int  # 收藏时间戳
    fav_folder: str
    fav_folder_id: int
    play_count: int
    collect_count: int
    # 统计数据
    like_count: int = 0
    coin_count: int = 0
    share_count: int = 0
    danmaku_count: int = 0
    reply_count: int = 0
    # 新增元数据
    pubdate: int = 0  # 发布时间戳
    tname: str = ""  # 分区名称
    author_sign: str = ""  # UP主简介

    def __post_init__(self) -> None:
        """数据清理和验证"""
        if self.intro and len(self.intro) > 200:
            self.intro = self.intro[:200] + "..."
        if self.author_sign and len(self.author_sign) > 100:
            self.author_sign = self.author_sign[:100] + "..."


@dataclass
class WatchProgress:
    """观看进度数据类"""
    bvid: str
    progress: int  # 当前播放进度（秒）
    duration: int  # 视频总时长（秒）
    view_at: int  # 观看时间戳
    page: int  # 分P页码

    @property
    def progress_percent(self) -> int:
        """计算观看进度百分比"""
        if not self.duration:
            return 0
        return min(int((self.progress / self.duration) * 100), 100)


@dataclass
class UpInfo:
    """UP主信息数据类"""
    mid: int
    name: str
    face: str  # 头像URL
    sign: str  # 签名/简介
    fans: int = 0
    videos: int = 0  # 投稿数
    level: int = 0
    official: str = ""  # 认证信息

    @property
    def is_verified(self) -> bool:
        """是否已认证"""
        return bool(self.official)

    @property
    def fans_display(self) -> str:
        """格式化显示粉丝数"""
        if self.fans >= 10000:
            return f"{self.fans / 10000:.1f}万"
        return str(self.fans)



class BilibiliAPIError(Exception):
    """B站API基础异常"""
    pass


class CookieExpiredError(BilibiliAPIError):
    """Cookie已过期"""
    pass


class RateLimitError(BilibiliAPIError):
    """请求频率限制"""
    pass


class AntiCrawlError(BilibiliAPIError):
    """反爬机制触发"""
    pass


class NetworkError(BilibiliAPIError):
    """网络连接错误"""
    pass


class APIResponseError(BilibiliAPIError):
    """API响应异常"""
    pass



class BilibiliAPI:
    """B站 API 封装类

    提供 B站 API 的统一访问接口，包含：
    - 自动重试机制
    - 请求频率控制
    - 统一错误处理
    """

    API_BASE = "https://api.bilibili.com"

    # 默认请求配置
    DEFAULT_TIMEOUT = 10  # 秒
    DEFAULT_RETRY_DELAY = 1.5  # 秒
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        cookie: str,
        timeout: int = DEFAULT_TIMEOUT,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        """初始化 API 客户端

        Args:
            cookie: B站 Cookie 字符串
            timeout: 请求超时时间（秒）
            retry_delay: 重试基础延迟（秒）
            max_retries: 最大重试次数
        """
        self.cookie = cookie
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries

        self.headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

        # 请求统计
        self._request_count = 0
        self._error_count = 0

    @property
    def request_count(self) -> int:
        """获取请求总数"""
        return self._request_count

    @property
    def error_count(self) -> int:
        """获取错误总数"""
        return self._error_count

    def _build_url(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """构建完整URL

        Args:
            endpoint: API端点路径
            params: 查询参数

        Returns:
            完整的请求URL
        """
        url = f"{self.API_BASE}{endpoint}"
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            if param_str:
                url = f"{url}?{param_str}"
        return url

    def _request(
        self,
        url: str,
        method: str = "GET",
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """发起 HTTP 请求（带重试机制）

        Args:
            url: 请求URL
            method: HTTP方法
            max_retries: 最大重试次数（可选，默认使用实例配置）

        Returns:
            API响应数据

        Raises:
            AntiCrawlError: 反爬机制触发
            RateLimitError: 请求频率限制
            CookieExpiredError: Cookie已过期
            NetworkError: 网络连接错误
            APIResponseError: API响应异常
        """
        if max_retries is None:
            max_retries = self.max_retries

        last_exception: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                # 请求前延迟（递增策略避免限流）
                delay = self.retry_delay + attempt * 1.0
                time.sleep(delay)

                self._request_count += 1
                logger.debug(f"请求 {self._request_count}: {url}")

                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=self.timeout
                )

                # 检查HTTP状态码
                if response.status_code == 412:
                    raise AntiCrawlError("反爬机制触发 (HTTP 412)")

                if response.status_code == 429:
                    raise RateLimitError("请求频率限制 (HTTP 429)")

                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code}, 重试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        continue
                    raise APIResponseError(f"HTTP错误: {response.status_code}")

                # 检查空响应
                if not response.text:
                    logger.warning(f"空响应, 重试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        continue
                    raise APIResponseError("服务器返回空响应")

                # 解析JSON
                data = response.json()

                # 检查API返回码
                code = data.get("code", 0)
                if code == -101:
                    raise CookieExpiredError("Cookie已过期或未登录")
                elif code == -400:
                    raise APIResponseError(f"请求参数错误: {data.get('message', '未知')}")
                elif code == -403:
                    raise APIResponseError(f"权限不足: {data.get('message', '未知')}")
                elif code != 0:
                    raise APIResponseError(f"API错误 [{code}]: {data.get('message', '未知')}")

                return data.get("data", {})

            except (AntiCrawlError, RateLimitError, CookieExpiredError):
                # 这些错误不应该重试
                raise

            except (Timeout, ConnectionError) as e:
                last_exception = NetworkError(f"网络连接错误: {e}")
                logger.warning(f"网络错误, 重试 {attempt + 1}/{max_retries}: {e}")

            except requests.exceptions.JSONDecodeError as e:
                last_exception = APIResponseError(f"JSON解析错误: {e}")
                logger.warning(f"响应解析失败, 重试 {attempt + 1}/{max_retries}")

            except RequestException as e:
                last_exception = NetworkError(f"请求异常: {e}")
                logger.warning(f"请求失败, 重试 {attempt + 1}/{max_retries}: {e}")

            self._error_count += 1

            if attempt < max_retries - 1:
                continue

        # 所有重试都失败了
        if last_exception:
            raise last_exception
        raise APIResponseError("请求失败，已达最大重试次数")

    def validate_cookie(self) -> Dict[str, Any]:
        """验证 Cookie 是否有效

        Returns:
            包含验证结果的字典：
            - valid: bool - 是否有效
            - mid: int - 用户ID
            - name: str - 用户名
            - error: str - 错误信息（如果无效）
        """
        try:
            url = f"{self.API_BASE}/x/web-interface/nav"
            data = self._request(url)

            return {
                "valid": True,
                "mid": data.get("mid"),
                "name": data.get("uname"),
                "vip_status": data.get("vipStatus", False)
            }

        except CookieExpiredError as e:
            return {"valid": False, "error": str(e)}

        except Exception as e:
            logger.error(f"验证Cookie失败: {e}")
            return {"valid": False, "error": str(e)}

    
    def get_favorite_folders(self, mid: int) -> Dict[str, Any]:
        """获取用户收藏夹列表

        Args:
            mid: 用户ID

        Returns:
            收藏夹列表数据
        """
        url = f"{self.API_BASE}/x/v3/fav/folder/created/list-all?up_mid={mid}"
        return self._request(url)

    def get_folder_videos(
        self,
        media_id: int,
        pn: int = 1,
        ps: int = 20
    ) -> Dict[str, Any]:
        """获取收藏夹内的视频列表

        Args:
            media_id: 收藏夹ID
            pn: 页码（从1开始）
            ps: 每页数量（最大20）

        Returns:
            视频列表数据
        """
        url = f"{self.API_BASE}/x/v3/fav/resource/list?media_id={media_id}&pn={pn}&ps={ps}"
        return self._request(url)

    def get_all_favorite_videos(self, mid: int) -> tuple:
        """获取所有收藏视频

        Args:
            mid: 用户ID

        Returns:
            元组：(收藏夹列表, 视频列表, 收藏夹视频数量映射)
        """
        folders_data = self.get_favorite_folders(mid)
        folders = folders_data.get("list", [])

        all_videos: List[VideoInfo] = []
        folder_counts: Dict[int, int] = {}

        for folder in folders:
            folder_id = folder.get("id")
            folder_name = folder.get("title", "")
            media_count = folder.get("media_count", 0)

            logger.info(f"处理收藏夹: {folder_name} ({media_count}个视频)")
            print(f"   - {folder_name} ({media_count}个视频)")

            # 计算需要的页数
            page_count = (media_count + ps - 1) // ps if (ps := 20) else 1
            folder_video_count = 0

            for pn in range(1, page_count + 1):
                result = self.get_folder_videos(folder_id, pn, 20)
                medias = result.get("medias", [])

                for video in medias:
                    if not video.get("bvid"):
                        continue

                    try:
                        upper = video.get("upper", {})
                        cnt_info = video.get("cnt_info", {})

                        video_info = VideoInfo(
                            bvid=video["bvid"],
                            title=video.get("title", ""),
                            intro=video.get("intro") or "",
                            duration=video.get("duration", 0),
                            author=upper.get("name", ""),
                            author_id=upper.get("mid", 0),
                            cover=video.get("cover", ""),
                            fav_time=video.get("fav_time", 0),
                            fav_folder=folder_name,
                            fav_folder_id=folder_id,
                            play_count=cnt_info.get("play", 0),
                            collect_count=cnt_info.get("collect", 0),
                            # 收藏夹API返回的数据中没有这些字段，需要单独调用详情API
                            like_count=0,
                            coin_count=0,
                            share_count=0,
                            danmaku_count=0,
                            author_sign=upper.get("sign", "") or ""  # UP主签名
                        )
                        all_videos.append(video_info)
                        folder_video_count += 1

                    except Exception as e:
                        logger.warning(f"解析视频数据失败: {e}")
                        continue

            folder_counts[folder_id] = folder_video_count

        return folders, all_videos, folder_counts

    def enrich_video_stats(
        self,
        video: VideoInfo,
        delay: float = 1.5
    ) -> VideoInfo:
        """补充视频的完整统计数据

        Args:
            video: 视频信息对象
            delay: 请求延迟（秒）

        Returns:
            更新后的视频信息对象
        """
        try:
            time.sleep(delay)
            detail = self.get_video_detail(video.bvid)
            stat = detail.get("stat", {})
            owner = detail.get("owner", {})

            # 更新统计数据
            video.like_count = stat.get("like", 0) or 0
            video.coin_count = stat.get("coin", 0) or 0
            video.share_count = stat.get("share", 0) or 0
            video.danmaku_count = stat.get("danmaku", 0) or 0
            video.reply_count = stat.get("reply", 0) or 0

            if stat.get("view", 0):
                video.play_count = stat.get("view", 0)

            # 更新元数据
            video.pubdate = detail.get("pubdate", 0) or 0
            video.tname = detail.get("tname_v2") or detail.get("tname") or ""

            # 更新简介（详情API的desc更准确）
            if detail.get("desc"):
                desc = detail.get("desc", "")
                video.intro = desc[:200] + "..." if len(desc) > 200 else desc

            # 更新UP主签名
            if owner.get("sign"):
                video.author_sign = owner.get("sign", "")[:100]

            logger.debug(f"补充统计成功: {video.bvid}")

        except Exception as e:
            logger.warning(f"补充统计失败: {video.bvid} - {e}")

        return video

    def enrich_videos_batch(
        self,
        videos: List[VideoInfo],
        delay: float = 1.5,
        progress_callback: Optional[callable] = None
    ) -> List[VideoInfo]:
        """批量补充视频统计数据

        Args:
            videos: 视频列表
            delay: 请求延迟（秒）
            progress_callback: 进度回调函数

        Returns:
            更新后的视频列表
        """
        total = len(videos)
        for i, video in enumerate(videos):
            if progress_callback:
                progress_callback(i + 1, total, video.bvid)
            self.enrich_video_stats(video, delay)

        return videos

    def get_video_detail(self, bvid: str) -> Dict[str, Any]:
        """获取视频详情

        Args:
            bvid: 视频BV号

        Returns:
            视频详情数据
        """
        url = f"{self.API_BASE}/x/web-interface/view?bvid={bvid}"
        return self._request(url)

    def get_video_pages(self, bvid: str) -> List[Dict[str, Any]]:
        """获取视频分P列表

        Args:
            bvid: 视频BV号

        Returns:
            分P列表
        """
        detail = self.get_video_detail(bvid)
        return detail.get("pages", [])

    def get_video_chapters(self, bvid: str) -> List[Dict[str, Any]]:
        """获取视频章节列表

        Args:
            bvid: 视频BV号

        Returns:
            章节列表
        """
        detail = self.get_video_detail(bvid)
        return detail.get("chapters", [])

    def get_video_subtitle(self, bvid: str, cid: Optional[int] = None) -> Dict[str, Any]:
        """获取视频字幕

        Args:
            bvid: 视频BV号
            cid: 视频cid（可选，不传则自动获取）

        Returns:
            字幕数据
        """
        if not cid:
            detail = self.get_video_detail(bvid)
            cid = detail.get("cid", 0)

        url = f"{self.API_BASE}/x/player/v2?bvid={bvid}&cid={cid}"
        return self._request(url)

    
    def get_history(self, pn: int = 1, ps: int = 50) -> List[Dict[str, Any]]:
        """获取观看历史

        Args:
            pn: 页码（从1开始）
            ps: 每页数量（最大50）

        Returns:
            观看历史列表
        """
        url = f"{self.API_BASE}/x/v2/history?pn={pn}&ps={ps}"
        data = self._request(url)

        # 处理不同的返回格式
        if isinstance(data, list):
            return data
        return data.get("list", []) if isinstance(data, dict) else []

    def get_watch_progress_map(
        self,
        max_pages: int = 10
    ) -> Dict[str, WatchProgress]:
        """获取观看进度映射表

        Args:
            max_pages: 最大获取页数

        Returns:
            BV号到观看进度的映射字典
        """
        watch_map: Dict[str, WatchProgress] = {}

        for pn in range(1, max_pages + 1):
            history = self.get_history(pn, 50)

            if not history:
                break

            for item in history:
                bvid = item.get("bvid")
                if not bvid:
                    continue

                try:
                    page_info = item.get("page", {})

                    watch_progress = WatchProgress(
                        bvid=bvid,
                        progress=item.get("progress") or 0,
                        duration=item.get("duration") or 0,
                        view_at=item.get("view_at", 0),
                        page=page_info.get("page", 1)
                    )
                    watch_map[bvid] = watch_progress

                except Exception as e:
                    logger.warning(f"解析观看记录失败 {bvid}: {e}")
                    continue

            if len(history) < 50:
                break

        return watch_map

    
    def get_followings(self, mid: int, pn: int = 1, ps: int = 50) -> List[Dict[str, Any]]:
        """获取关注列表

        Args:
            mid: 用户ID
            pn: 页码（从1开始）
            ps: 每页数量（最大50）

        Returns:
            关注列表
        """
        url = f"{self.API_BASE}/x/relation/followings?vmid={mid}&pn={pn}&ps={ps}&order=desc"
        data = self._request(url)

        # 处理不同的返回结构
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            followings = data.get("list", {})
            if isinstance(followings, dict):
                return followings.get("followings", [])
            if isinstance(followings, list):
                return followings
            if "followings" in data:
                return data["followings"]

        return []

    def get_all_followings(self, mid: int) -> List[UpInfo]:
        """获取所有关注的UP主

        Args:
            mid: 用户ID

        Returns:
            UP主信息列表
        """
        all_followings: List[UpInfo] = []
        pn = 1

        while True:
            followings = self.get_followings(mid, pn, 50)

            if not followings:
                break

            for up in followings:
                if not isinstance(up, dict):
                    continue

                try:
                    up_info = self._parse_up_info(up)
                    all_followings.append(up_info)

                except Exception as e:
                    logger.warning(f"解析UP主数据失败: {e}")
                    continue

            if len(followings) < 50:
                break

            pn += 1
            logger.info(f"已获取 {len(all_followings)} 个关注")
            print(f"   已获取 {len(all_followings)} 个关注...")

        return all_followings

    def _parse_up_info(self, up: Dict[str, Any]) -> UpInfo:
        """解析UP主信息

        Args:
            up: 原始UP主数据字典

        Returns:
            UpInfo对象
        """
        # 处理 official 字段（可能是 dict 或 string）
        official_val = up.get("official", "")
        if isinstance(official_val, dict):
            official_str = official_val.get("title", "")
        else:
            official_str = str(official_val) if official_val else ""

        return UpInfo(
            mid=up.get("mid", 0),
            name=up.get("uname") or up.get("name", ""),
            face=up.get("face", ""),
            sign=up.get("sign", ""),
            fans=up.get("fans") or up.get("follower") or 0,
            videos=up.get("videos") or up.get("video_count") or 0,
            level=up.get("level") or 0,
            official=official_str
        )

    def get_up_info(self, mid: int) -> UpInfo:
        """获取UP主详细信息

        Args:
            mid: UP主ID

        Returns:
            UP主信息对象
        """
        url = f"{self.API_BASE}/x/space/acc/info?mid={mid}"
        data = self._request(url)

        official_data = data.get("official", {})
        official_str = official_data.get("title", "") if isinstance(official_data, dict) else ""

        return UpInfo(
            mid=data.get("mid", 0),
            name=data.get("name", ""),
            face=data.get("face", ""),
            sign=data.get("sign", ""),
            fans=data.get("fans") or data.get("follower") or 0,
            videos=data.get("videos", 0),
            level=data.get("level", 0),
            official=official_str
        )

    def get_up_videos(
        self,
        mid: int,
        pn: int = 1,
        ps: int = 30
    ) -> Dict[str, Any]:
        """获取UP主的视频列表

        Args:
            mid: UP主ID
            pn: 页码（从1开始）
            ps: 每页数量

        Returns:
            视频列表数据
        """
        url = f"{self.API_BASE}/x/space/arc/search?mid={mid}&pn={pn}&ps={ps}"
        return self._request(url)

    def get_following_count(self, mid: int) -> int:
        """获取关注数量

        Args:
            mid: 用户ID

        Returns:
            关注数量
        """
        url = f"{self.API_BASE}/x/relation/stat?vmid={mid}"
        data = self._request(url)
        return data.get("following", 0)

    def search_in_followings(
        self,
        mid: int,
        keyword: str
    ) -> List[UpInfo]:
        """在关注列表中搜索UP主

        Args:
            mid: 用户ID
            keyword: 搜索关键词

        Returns:
            匹配的UP主列表
        """
        all_followings = self.get_all_followings(mid)
        keyword_lower = keyword.lower()

        matched = [
            up for up in all_followings
            if keyword_lower in up.name.lower()
            or keyword_lower in up.sign.lower()
        ]

        return matched
