# coding=utf-8
# !/usr/bin/python
import sys, re
import base64
import hashlib
import requests
from typing import Tuple
from base.spider import Spider
from datetime import datetime, timedelta
from urllib.parse import quote, unquote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
sys.path.append('..')

# 搜索用户名，关键词格式为“类别+空格+关键词”
# 类别在标签上已注明，比如“女主播g”，则搜索类别为“g”
# 搜索“g per”，则在“女主播”中搜索“per”, 关键词不区分大小写，但至少3位，否则空结果

class Spider(Spider):

    def init(self, extend="{}"):
        # 上游版本使用 stripchat 主站；如果你需要保留 stripol，可在这里改回去
        origin = 'https://zh.stripchat.com'
        self.host = origin
        self.headers = {
            'Origin': origin,
            'Referer': f"{origin}/",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0'
        }
        self.stripchat_key = self.decode_key_compact()
        # 缓存字典
        self._hash_cache = {}
        self.create_session_with_retry()

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeContent(self, filter):
        result = {}
        classes = [{'type_name': '女主播g', 'type_id': 'girls'}, {'type_name': '情侣c', 'type_id': 'couples'}, {'type_name': '男主播m', 'type_id': 'men'}, {'type_name': '跨性别t', 'type_id': 'trans'}]
        filters = {}
        value = [{'n': '中国', 'v': 'tagLanguageChinese'}, {'n': '亚洲', 'v': 'ethnicityAsian'}, {'n': '白人', 'v': 'ethnicityWhite'}, {'n': '拉丁', 'v': 'ethnicityLatino'}, {'n': '混血', 'v': 'ethnicityMultiracial'}, {'n': '印度', 'v': 'ethnicityIndian'}, {'n': '阿拉伯', 'v': 'ethnicityMiddleEastern'}, {'n': '黑人', 'v': 'ethnicityEbony'}]
        value_gay = [{'n': '情侣', 'v': 'sexGayCouples'}, {'n': '直男', 'v': 'orientationStraight'}]
        for tid in ['girls', 'couples', 'men', 'trans']:
            c_value = value[:]
            if tid == 'men':
                c_value += value_gay
            filters[tid] = [{'key': 'tag', 'value': c_value}]
        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        limit = 60
        offset = limit * (int(pg) - 1)
        domain = f"{self.host}/api/front/models?improveTs=false&removeShows=false&limit={limit}&offset={offset}&primaryTag={tid}&sortBy=stripRanking&rcmGrp=A&rbCnGr=true&prxCnGr=false&nic=false"
        if 'tag' in extend:
            domain += "&filterGroupTags=%5B%5B%22" + extend['tag'] + "%22%5D%5D"
        rsp = self.fetch(domain).json()
        videos = [
            {
                "vod_id": str(vod['username']).strip(),
                "vod_name": f"{self.country_code_to_flag(str(vod['country']).strip())}{str(vod['username']).strip()}",
                "vod_pic": f"https://img.doppiocdn.net/thumbs/{vod['snapshotTimestamp']}/{vod['id']}",
                "vod_remarks": "" if vod.get('status') == "public" else "🎫"
            }
            for vod in rsp.get('models', [])
        ]
        total = int(rsp.get('filteredCount', 0))
        return {
            "list": videos,
            "page": pg,
            "pagecount": (total + limit - 1) // limit,
            "limit": limit,
            "total": total
        }

    def detailContent(self, array):
        username = array[0]
        rsp = self.fetch(f"{self.host}/api/front/v2/models/username/{username}/cam").json()
        info = rsp['cam']
        user = rsp['user']['user']
        id = str(user['id'])
        country = str(user['country']).strip()
        isLive = "" if user['isLive'] else " 已下播"
        flag = self.country_code_to_flag(country)
        remark, startAt = '', ''
        # 兼容不同字段结构
        if show := info.get('show'):
            startAt = show.get('createdAt') or show.get('startAt')
            # 有些结构会更深一层
            if not startAt and isinstance(show.get('details'), dict):
                gs = show['details'].get('groupShow') if isinstance(show['details'].get('groupShow'), dict) else None
                if gs:
                    startAt = gs.get('startAt') or gs.get('createdAt')
        elif show := info.get('groupShowAnnouncement'):
            startAt = show.get('startAt')
        if startAt:
            BJtime = (datetime.strptime(startAt, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=8)).strftime("%m月%d日 %H:%M")
            remark = f"🎫 始于 {BJtime}"
        vod = [{
            "vod_id": id,
            "vod_name": str(info['topic']).strip(), 
            "vod_pic": str(user['avatarUrl']),
            "vod_director": f"{flag}{username}{isLive}",
            "vod_remarks": remark,
            'vod_play_from': '书生玩剣ⁱ·*₁＇',
            'vod_play_url': f"{id}${id}"
        }]
        result = {}
        result['list'] = vod
        return result

    def process_key(self, key: str) -> Tuple[str, str]:
        tags = {'G': 'girls', 'C': 'couples', 'M': 'men', 'T': 'trans'}
        parts = key.split(maxsplit=1)  # 仅分割第一个空格
        if len(parts) > 1 and tags.get(parts[0].upper(), ''):
            return tags[parts[0].upper()], parts[1].strip()
        return 'girls', key.strip()

    def searchContent(self, key, quick, pg="1"):
        result = {}
        if int(pg) > 1:
            return result
        tag, key = self.process_key(key)
        domain = f"{self.host}/api/front/v4/models/search/group/username?query={key}&limit=900&primaryTag={tag}"
        rsp = self.fetch(domain).json()
        result['list'] = [
            {
                "vod_id": str(user['username']).strip(),
                "vod_name": f"{self.country_code_to_flag(str(user['country']).strip())}{user['username']}",
                "vod_pic": f"https://img.doppiocdn.net/thumbs/{user['snapshotTimestamp']}/{user['id']}",
                "vod_remarks": "" if user.get('status') == "public" else "🎫"
            }
            for user in rsp.get('models', [])
            if user.get('isLive')
        ]
        return result

    def playerContent(self, flag, id, vipFlags):
        """
        播放优化（解决超时）：
        1. 只请求 1 个 master，超时 5s，不做多 CDN 串行重试
        2. 默认返回 480p/240p 直链（不走 proxy://，避免壳二次回源超时）
        3. 仅在直链解析失败时回退 master 直链
        """
        master_url = f"https://edge-hls.doppiocdn.net/hls/{id}/master/{id}_auto.m3u8?playlistType=lowLatency"
        play_headers = {
            "User-Agent": self.headers.get("User-Agent", ""),
            "Origin": self.host,
            "Referer": f"{self.host}/",
            "Accept": "*/*",
        }
        master_text = ""
        try:
            response = self.session.get(master_url, headers=self.headers, timeout=5)
            if response.status_code == 200 and "#EXTM3U" in response.text:
                master_text = response.text
        except Exception:
            master_text = ""

        if not master_text:
            # 快速失败：直接把 master 交给播放器，由播放器自己拉流
            return {
                "parse": 0,
                "url": master_url,
                "header": play_headers,
                "jx": 0,
            }

        psch = ""
        pkey = ""
        for line in master_text.splitlines():
            if line.startswith("#EXT-X-MOUFLON:"):
                parts = line.split(":")
                if len(parts) >= 4:
                    psch, pkey = parts[2], parts[3]

        quality_entries = []
        lines = master_text.splitlines()
        for index, line in enumerate(lines):
            if "#EXT-X-STREAM-INF" not in line or index + 1 >= len(lines):
                continue
            name_match = re.search(r'NAME="([^"]+)"', line)
            quality_name = name_match.group(1) if name_match else f"q{index}"
            stream_url = lines[index + 1].strip()
            if not stream_url or stream_url.startswith("#"):
                continue
            if "psch=" not in stream_url and psch:
                separator = "&" if "?" in stream_url else "?"
                stream_url = f"{stream_url}{separator}psch={psch}&pkey={pkey}"
            quality_entries.append((quality_name, stream_url))

        if not quality_entries:
            return {"parse": 0, "url": master_url, "header": play_headers, "jx": 0}

        preferred_order = ["480", "240", "360", "720", "160", "source", "1080"]

        def quality_rank(name: str) -> int:
            lower_name = (name or "").lower()
            for rank, token in enumerate(preferred_order):
                if token in lower_name:
                    return rank
            return 50

        quality_entries.sort(key=lambda item: quality_rank(item[0]))
        best_name, best_url = quality_entries[0]

        # 主返回：单一直链，最快；附加 1~2 个备选直链（不走 py 代理）
        url_list = [best_name, best_url]
        for quality_name, stream_url in quality_entries[1:3]:
            url_list.extend([quality_name, stream_url])
        url_list.extend(["master", master_url])

        return {
            "parse": 0,
            "url": url_list,
            "contentType": "",
            "header": play_headers,
            "jx": 0,
        }

    def localProxy(self, param):
        # 保留兼容：若壳仍走 proxy:// 也能工作，但默认播放已不再依赖它
        url = unquote(param.get("url") or "")
        if not url:
            return [404, "text/plain", "missing url"]
        try:
            data = self.session.get(url, headers=self.headers, timeout=5)
        except Exception:
            return [504, "text/plain", "upstream timeout"]
        if data.status_code == 403:
            degraded = re.sub(r"\d+p\d*\.m3u8", "160p_blurred.m3u8", url)
            try:
                data = self.session.get(degraded, headers=self.headers, timeout=5)
            except Exception:
                return [403, "text/plain", "forbidden"]
        if data.status_code != 200:
            return [data.status_code, "text/plain", f"upstream {data.status_code}"]
        body = data.text
        if "#EXT-X-MOUFLON:FILE" in body:
            body = self.process_m3u8_content_v2(body)
        return [200, "application/vnd.apple.mpegurl", body]

    def process_m3u8_content_v2(self, m3u8_content):
        lines = m3u8_content.strip().split("\n")
        for index, line in enumerate(lines):
            if not line.startswith("#EXT-X-MOUFLON:FILE:"):
                continue
            if index + 1 >= len(lines):
                continue
            encrypted_data = line.split(":", 2)[2].strip()
            decrypted_data = None
            for candidate_key in [self.stripchat_key, "Zokee2OhPh9kugh4", "Quean4cai9boJa5a"]:
                try:
                    decrypted_data = self.decrypt(encrypted_data, candidate_key)
                    break
                except Exception:
                    continue
            if not decrypted_data:
                continue
            if "media.mp4" in lines[index + 1]:
                lines[index + 1] = lines[index + 1].replace("media.mp4", decrypted_data)
            else:
                # 兼容非 media.mp4 占位
                lines[index + 1] = decrypted_data
        return "\n".join(lines)

    def country_code_to_flag(self, country_code):
        if len(country_code) != 2 or not country_code.isalpha():
            return country_code
        flag_emoji = ''.join([chr(ord(c.upper()) - ord('A') + 0x1F1E6) for c in country_code])
        return flag_emoji

    def decode_key_compact(self):
        base64_str = "NTEgNzUgNjUgNjEgNmUgMzQgNjMgNjEgNjkgMzkgNjIgNmYgNGEgNjEgMzUgNjE="
        decoded = base64.b64decode(base64_str).decode('utf-8')
        key_bytes = bytes(int(hex_str, 16) for hex_str in decoded.split(" "))
        return key_bytes.decode('utf-8')

    def compute_hash(self, key: str) -> bytes:
        """计算并缓存SHA-256哈希"""
        if key not in self._hash_cache:
            sha256 = hashlib.sha256()
            sha256.update(key.encode('utf-8'))
            self._hash_cache[key] = sha256.digest()
        return self._hash_cache[key]

    def decrypt(self, encrypted_b64: str, key: str) -> str:
        """解密Base64编码的密文"""
        # 修复Base64填充
        padding = len(encrypted_b64) % 4
        if padding:
            encrypted_b64 += '=' * (4 - padding)
    
        # 计算哈希并解密
        hash_bytes = self.compute_hash(key)
        encrypted_data = base64.b64decode(encrypted_b64)

        # 异或解密
        decrypted_bytes = bytearray()
        for i, cipher_byte in enumerate(encrypted_data):
            key_byte = hash_bytes[i % len(hash_bytes)]
            decrypted_bytes.append(cipher_byte ^ key_byte)
        return decrypted_bytes.decode('utf-8')

    def create_session_with_retry(self, retries=1, backoff_factor=0.1):
        # 播放链路要快：少重试，避免 App 侧总超时
        self.session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self, url):
        return self.session.get(url, headers=self.headers, timeout=8)
