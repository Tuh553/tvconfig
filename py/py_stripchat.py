# coding=utf-8
# !/usr/bin/python
import sys, re
import base64
import hashlib
import requests
from typing import Tuple
from base.spider import Spider
from datetime import datetime, timedelta
from urllib.parse import quote, unquote, urljoin
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
        Stripchat 播放关键：

        1. 子播放列表必须带 psch/pkey，否则 CDN 返回 #EXT-X-MOUFLON-ADVERT（广告）
        2. 分片路径被写成 media.mp4 占位，真实地址在 #EXT-X-MOUFLON:URI:...
           必须走 proxy:// 由 localProxy 替换，直链播放会 404/超时
        3. 优先非 lowLatency 列表（结构更简单，兼容性更好）
        4. 绝不把裸 master 交给播放器（播放器跟线路时会丢 psch → 广告）
        """
        play_headers = {
            "User-Agent": self.headers.get("User-Agent", ""),
            "Origin": self.host,
            "Referer": f"{self.host}/",
            "Accept": "*/*",
        }
        master_candidates = [
            f"https://edge-hls.doppiocdn.net/hls/{id}/master/{id}_auto.m3u8",
            f"https://edge-hls.doppiocdn.net/hls/{id}/master/{id}.m3u8",
            f"https://edge-hls.doppiocdn.org/hls/{id}/master/{id}_auto.m3u8",
            f"https://edge-hls.doppiocdn.net/hls/{id}/master/{id}_auto.m3u8?playlistType=lowLatency",
        ]
        master_text = ""
        for master_url in master_candidates:
            try:
                response = self.session.get(master_url, headers=self.headers, timeout=6)
                if response.status_code == 200 and "#EXTM3U" in response.text:
                    master_text = response.text
                    break
            except Exception:
                continue

        if not master_text:
            return {
                "parse": 0,
                "url": "",
                "header": play_headers,
                "jx": 0,
                "msg": "master fetch failed",
            }

        psch = ""
        pkey = ""
        for line in master_text.splitlines():
            if line.startswith("#EXT-X-MOUFLON:PSCH:"):
                parts = line.split(":")
                if len(parts) >= 4:
                    # 取最后一个 psch/pkey（与媒体列表一致）
                    psch, pkey = parts[2], parts[3]
            elif line.startswith("#EXT-X-MOUFLON:"):
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
            # 去掉 lowLatency，拿到普通 HLS（分片为完整段，更稳）
            stream_url = stream_url.replace("playlistType=lowLatency&", "").replace(
                "playlistType=lowLatency", ""
            )
            stream_url = stream_url.rstrip("?&")
            # 必须带 psch/pkey，否则是广告
            if psch and "psch=" not in stream_url:
                separator = "&" if "?" in stream_url else "?"
                stream_url = f"{stream_url}{separator}psch={psch}&pkey={pkey}"
            elif psch and "pkey=" not in stream_url:
                stream_url = f"{stream_url}&pkey={pkey}"
            # 强制走本地代理做 MOUFLON 替换
            proxy_url = f"{self.getProxyUrl()}&url={quote(stream_url, safe='')}"
            quality_entries.append((quality_name, proxy_url))

        if not quality_entries:
            return {
                "parse": 0,
                "url": "",
                "header": play_headers,
                "jx": 0,
                "msg": "no stream variants",
            }

        preferred_order = ["480", "240", "360", "720", "160", "source", "1080"]

        def quality_rank(name: str) -> int:
            lower_name = (name or "").lower()
            for rank, token in enumerate(preferred_order):
                if token in lower_name:
                    return rank
            return 50

        quality_entries.sort(key=lambda item: quality_rank(item[0]))

        url_list = []
        for quality_name, proxy_url in quality_entries:
            url_list.extend([quality_name, proxy_url])

        return {
            "parse": 0,
            "url": url_list,
            "contentType": "",
            "header": play_headers,
            "jx": 0,
        }

    def localProxy(self, param):
        url = unquote(param.get("url") or "")
        if not url:
            return [404, "text/plain", "missing url"]
        try:
            data = self.session.get(url, headers=self.headers, timeout=8)
        except Exception:
            return [504, "text/plain", "upstream timeout"]
        if data.status_code == 403:
            degraded = re.sub(r"\d+p\d*\.m3u8", "160p_blurred.m3u8", url)
            try:
                data = self.session.get(degraded, headers=self.headers, timeout=8)
            except Exception:
                return [403, "text/plain", "forbidden"]
        if data.status_code != 200:
            return [data.status_code, "text/plain", f"upstream {data.status_code}"]
        body = data.text or ""
        # 广告列表直接拒绝，避免“能播但只有广告”
        if "#EXT-X-MOUFLON-ADVERT" in body:
            return [403, "text/plain", "advert playlist (missing psch/pkey)"]
        if "#EXT-X-MOUFLON:" in body:
            body = self.process_m3u8_content_v2(body)
        body = self.simplify_ll_hls(body)
        body = self.absolutize_m3u8(url, body)
        return [200, "application/vnd.apple.mpegurl", body]

    def simplify_ll_hls(self, m3u8_content: str) -> str:
        """去掉 LL-HLS 的 PART/PRELOAD 等，只保留标准 EXTINF 分片，提升兼容性。"""
        if not m3u8_content:
            return m3u8_content
        drop_prefixes = (
            "#EXT-X-PART:",
            "#EXT-X-PART-INF:",
            "#EXT-X-PRELOAD-HINT:",
            "#EXT-X-RENDITION-REPORT:",
            "#EXT-X-SERVER-CONTROL:",
            "#EXT-X-MOUFLON:",
        )
        out_lines = []
        for line in m3u8_content.splitlines():
            stripped = line.strip()
            if any(stripped.startswith(prefix) for prefix in drop_prefixes):
                continue
            out_lines.append(line)
        return "\n".join(out_lines)

    def absolutize_m3u8(self, playlist_url: str, m3u8_content: str) -> str:
        if not m3u8_content:
            return m3u8_content
        out_lines = []
        for line in m3u8_content.splitlines():
            raw = line.strip()
            if not raw:
                out_lines.append(line)
                continue
            if raw.startswith("#"):
                # #EXT-X-MAP:URI="relative"
                if 'URI="' in raw:
                    def _abs_uri(match):
                        uri_value = match.group(1)
                        if uri_value.startswith(("http://", "https://")):
                            return f'URI="{uri_value}"'
                        return f'URI="{urljoin(playlist_url, uri_value)}"'

                    raw = re.sub(r'URI="([^"]+)"', _abs_uri, raw)
                out_lines.append(raw)
                continue
            if raw.startswith(("http://", "https://")):
                out_lines.append(raw)
            else:
                out_lines.append(urljoin(playlist_url, raw))
        return "\n".join(out_lines)

    def encode_segment_url(self, segment_url: str) -> str:
        """
        分片名里常含 base64 的 + /，必须 percent-encode，
        否则 HTTP 会把 / 当路径分隔、把 + 当空格，导致 404。
        """
        if not segment_url or not segment_url.startswith("http"):
            return segment_url
        match = re.match(r"(https?://[^/]+/b-hls-\d+/\d+/)(.+)", segment_url)
        if not match:
            return segment_url
        return match.group(1) + quote(match.group(2), safe="")

    def process_m3u8_content_v2(self, m3u8_content):
        """
        处理 Stripchat MOUFLON 混淆：
        - 新：#EXT-X-MOUFLON:URI:<真实mp4> + 下一行 media.mp4 占位
        - 旧：#EXT-X-MOUFLON:FILE:<base64> + 下一行含 media.mp4（需 XOR 解密）
        """
        lines = m3u8_content.strip().split("\n")
        for index, line in enumerate(lines):
            if index + 1 >= len(lines):
                continue
            next_line = lines[index + 1]

            # 新格式：URI 直接给出真实分片
            if line.startswith("#EXT-X-MOUFLON:URI:") and "media.mp4" in next_line:
                real_url = self.encode_segment_url(line.split(":", 2)[2].strip())
                if 'URI="' in next_line:
                    lines[index + 1] = re.sub(
                        r'URI="[^"]*media\.mp4"',
                        f'URI="{real_url}"',
                        next_line,
                    )
                else:
                    lines[index + 1] = real_url
                continue

            # 旧格式：FILE 需解密
            if line.startswith("#EXT-X-MOUFLON:FILE:") and "media.mp4" in next_line:
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
                # 解密结果可能是相对路径或完整 URL
                if decrypted_data.startswith("http"):
                    replacement = self.encode_segment_url(decrypted_data)
                else:
                    replacement = quote(decrypted_data, safe="/")
                if 'URI="' in next_line:
                    lines[index + 1] = re.sub(
                        r'URI="[^"]*media\.mp4"',
                        f'URI="{replacement}"',
                        next_line,
                    )
                else:
                    lines[index + 1] = next_line.replace("media.mp4", replacement)
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
