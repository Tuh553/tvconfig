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

    # 与阅读订阅源 st.txt 一致：固定 pkey 才能拿到干净分片（无 media.mp4 混淆）
    FIXED_PKEYS = ["bXorqTB5ZhP5FcpX", "Iecohquahc5RieQu"]
    FALLBACK_CDN_HOSTS = [
        "doppiocdn.com",
        "doppiocdn.media",
        "doppiocdn.net",
        "doppiocdn.org",
        "doppiocdn.live",
    ]

    def init(self, extend="{}"):
        # 上游版本使用 stripchat 主站；如果你需要保留 stripol，可在这里改回去
        origin = 'https://zh.stripchat.com'
        self.host = origin
        self.headers = {
            'Origin': origin,
            'Referer': f"{origin}/",
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36'
        }
        self.stripchat_key = self.decode_key_compact()
        # 缓存字典
        self._hash_cache = {}
        self.cdn_hosts = list(self.FALLBACK_CDN_HOSTS)
        self.play_pkey = self.FIXED_PKEYS[0]
        self.create_session_with_retry()
        # 可选：extend 支持 {"proxy":"http://user:pass@host:port"}
        try:
            import json as _json
            ext = _json.loads(extend) if extend and extend not in ("{}", "") else {}
        except Exception:
            ext = {}
        proxy_url = (ext.get("proxy") or "").strip()
        if proxy_url:
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})
        # 预拉 CDN 列表（失败则用 fallback）
        try:
            self.refresh_cdn_hosts()
        except Exception:
            pass

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

    def refresh_cdn_hosts(self):
        """从官方 config 拉取 HLS CDN 列表（与 st.txt 一致）。"""
        response = self.session.get(
            f"{self.host}/api/front/v3/config/initial",
            headers=self.headers,
            timeout=8,
        )
        data = response.json() if response.status_code == 200 else {}
        hosts_map = ((data.get("initial") or {}).get("common") or {}).get("hlsStreamHosts") or {}
        ordered = []
        preferred_keys = ["A", "C", "D", "E", "F", "B", "A1", "C1", "D1", "E1", "F1", "B1"]
        dead_hosts = {"doppiocdn1.com"}
        for key in preferred_keys:
            host = hosts_map.get(key)
            if host and host not in ordered and host not in dead_hosts:
                ordered.append(host)
        for host in hosts_map.values():
            if host and host not in ordered and host not in dead_hosts:
                ordered.append(host)
        if ordered:
            self.cdn_hosts = ordered
        return self.cdn_hosts

    def build_master_url(self, stream_id: str, cdn_host: str, quality_suffix: str, pkey: str) -> str:
        """
        st.txt 播放地址格式：
        https://edge-hls.{cdn}/hls/{id}/master/{id}{suffix}.m3u8?pkey=固定值
        quality_suffix: _auto / _480p / _240p / ""(source)
        """
        return (
            f"https://edge-hls.{cdn_host}/hls/{stream_id}/master/"
            f"{stream_id}{quality_suffix}.m3u8?pkey={pkey}"
        )

    def playerContent(self, flag, id, vipFlags):
        """
        按阅读订阅源 st.txt 可播方案：

        - 使用固定 pkey（bXorqTB5ZhP5FcpX），不要用 master 里动态 PSCH
        - 使用 edge-hls.{cdn}/hls/{id}/master/{id}_{quality}.m3u8
        - 返回直链 master（自带 pkey 的子流），不走 proxy://
        - 本地实测：分片可直接 200 下载（无 media.mp4 混淆）
        """
        play_headers = {
            "User-Agent": self.headers.get("User-Agent", ""),
            "Origin": self.host,
            "Referer": f"{self.host}/",
            "Accept": "*/*",
        }
        stream_id = str(id).strip()
        if not stream_id:
            return {"parse": 0, "url": "", "header": play_headers, "jx": 0}

        # 确保 CDN 列表可用
        if not self.cdn_hosts:
            self.cdn_hosts = list(self.FALLBACK_CDN_HOSTS)
        pkey = self.play_pkey or self.FIXED_PKEYS[0]

        # 画质：auto 优先（master 内含 source/480p/240p 且已带 pkey）
        # 再给各画质 + 多线路兜底
        quality_plan = [
            ("auto", "_auto"),
            ("480p", "_480p"),
            ("240p", "_240p"),
            ("source", ""),
        ]
        url_list = []
        # 主线路：优先第一个 CDN 的 auto
        primary_cdn = self.cdn_hosts[0]
        primary_url = self.build_master_url(stream_id, primary_cdn, "_auto", pkey)
        url_list.extend(["auto", primary_url])

        # 其它画质（同一主 CDN）
        for quality_name, suffix in quality_plan[1:]:
            url_list.extend(
                [
                    quality_name,
                    self.build_master_url(stream_id, primary_cdn, suffix, pkey),
                ]
            )

        # 备用线路（其它 CDN 的 auto / 480p）
        for line_index, cdn_host in enumerate(self.cdn_hosts[1:4], start=2):
            url_list.extend(
                [
                    f"L{line_index}-auto",
                    self.build_master_url(stream_id, cdn_host, "_auto", pkey),
                ]
            )
            url_list.extend(
                [
                    f"L{line_index}-480p",
                    self.build_master_url(stream_id, cdn_host, "_480p", pkey),
                ]
            )

        # 备用 pkey（若主 pkey 失效）
        alt_pkey = self.FIXED_PKEYS[1] if len(self.FIXED_PKEYS) > 1 else ""
        if alt_pkey and alt_pkey != pkey:
            url_list.extend(
                [
                    "auto-altkey",
                    self.build_master_url(stream_id, primary_cdn, "_auto", alt_pkey),
                ]
            )

        return {
            "parse": 0,
            "url": url_list,
            "contentType": "",
            "header": play_headers,
            "jx": 0,
        }

    def localProxy(self, param):
        # 兼容旧缓存：若壳仍走 proxy://，尽量返回可播列表
        url = unquote(param.get("url") or "")
        if not url:
            return [404, "text/plain", "missing url"]
        # 强制补固定 pkey（st.txt 方案）
        if "pkey=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}pkey={self.play_pkey or self.FIXED_PKEYS[0]}"
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
        if "#EXT-X-MOUFLON-ADVERT" in body:
            return [403, "text/plain", "advert playlist"]
        # 若仍是混淆列表，尽量替换 URI
        if "#EXT-X-MOUFLON:URI:" in body or "#EXT-X-MOUFLON:FILE:" in body:
            body = self.process_m3u8_content_v2(body)
        return [200, "application/vnd.apple.mpegurl", body]

    def encode_segment_url(self, segment_url: str) -> str:
        if not segment_url or not segment_url.startswith("http"):
            return segment_url
        match = re.match(r"(https?://[^/]+/b-hls-\d+/\d+/)(.+)", segment_url)
        if not match:
            return segment_url
        return match.group(1) + quote(match.group(2), safe="")

    def process_m3u8_content_v2(self, m3u8_content):
        lines = m3u8_content.strip().split("\n")
        for index, line in enumerate(lines):
            if index + 1 >= len(lines):
                continue
            next_line = lines[index + 1]
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
                replacement = (
                    self.encode_segment_url(decrypted_data)
                    if decrypted_data.startswith("http")
                    else quote(decrypted_data, safe="/")
                )
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
