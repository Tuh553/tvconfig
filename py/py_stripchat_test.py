# coding=utf-8
# !/usr/bin/python
import os
import re
import sys
import base64
import hashlib
import json
import requests
from typing import Tuple
from datetime import datetime, timedelta
from urllib.parse import quote, unquote, urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 兼容：在 TVBox/CatVod 环境中通常由 jar 提供 base；本地执行时尝试补齐项目根目录路径
try:
    from base.spider import Spider as BaseSpider  # type: ignore
except ModuleNotFoundError:
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from base.spider import Spider as BaseSpider  # type: ignore

# 搜索用户名，关键词格式为“类别+空格+关键词”
# 类别在标签上已注明，比如“女主播g”，则搜索类别为“g”
# 搜索“g per”，则在“女主播”中搜索“per”, 关键词不区分大小写，但至少3位，否则空结果

class Spider(BaseSpider):

    def init(self, extend="{}"):
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
        self.debug = False
        self.timeout = 10
        try:
            ext = json.loads(extend) if extend else {}
            self.debug = bool(ext.get("debug", False))
            self.timeout = int(ext.get("timeout", 10) or 10)
        except Exception:
            self.debug = False
            self.timeout = 10
        self.create_session_with_retry()
        # 可选：为本地调试/特殊网络环境设置代理
        try:
            ext = json.loads(extend) if extend else {}
            proxy = ext.get("proxy")
            proxies = ext.get("proxies")
            if isinstance(proxies, dict) and proxies:
                self.session.proxies.update(proxies)
                self._dbg(f"session.proxies(dict)={proxies}")
            elif isinstance(proxy, str) and proxy.strip():
                p = proxy.strip()
                self.session.proxies.update({"http": p, "https": p})
                self._dbg(f"session.proxies(url)={p}")
        except Exception:
            pass
        return self

    def _dbg(self, msg: str):
        if getattr(self, "debug", False) and hasattr(self, "log"):
            try:
                self.log(f"[py_stripchat] {msg}")
            except Exception:
                pass

    def getName(self):
        return "StripChat 直播"

    def isVideoFormat(self, url):
        return bool(re.search(r'(m3u8|mp4)(?:\?|$)', url))

    def manualVideoCheck(self):
        return True

    def destroy(self):
        try:
            self.session.close()
        except Exception:
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
        return []

    def categoryContent(self, tid, pg, filter, extend):
        limit = 60
        offset = limit * (int(pg) - 1)
        domain = f"{self.host}/api/front/models?improveTs=false&removeShows=false&limit={limit}&offset={offset}&primaryTag={tid}&sortBy=stripRanking&rcmGrp=A&rbCnGr=true&prxCnGr=false&nic=false"
        if 'tag' in extend:
            domain += "&filterGroupTags=%5B%5B%22" + extend['tag'] + "%22%5D%5D"
        rsp = self.fetch(domain).json()
        vodList = rsp.get('models', [])
        videos = []
        for vod in vodList:
            id = str(vod['id'])
            name = str(vod['username']).strip()
            stamp = vod['snapshotTimestamp']
            country = str(vod['country']).strip()
            flag = self.country_code_to_flag(country)
            remark = "🎫" if vod['status'] == "groupShow" else ""
            videos.append({
                "vod_id": name,
                "vod_name": f"{flag}{name}",
                "vod_pic": f"https://img.doppiocdn.net/thumbs/{stamp}/{id}",
                "vod_remarks": remark
            })
        total = int(rsp.get('filteredCount', 0))
        result = {}
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = (total + limit - 1) // limit
        result['limit'] = limit
        result['total'] = total
        return result

    def detailContent(self, array):
        username = array[0]
        domain = f"{self.host}/api/front/v2/models/username/{username}/cam"
        rsp = self.fetch(domain).json()
        info = rsp['cam']
        user = rsp['user']['user']
        id = str(user['id'])
        country = str(user['country']).strip()
        isLive = "" if user['isLive'] else " 已下播"
        flag = self.country_code_to_flag(country)
        remark = ''
        startAt = ''
        if info.get('show') and info['show'].get('details') and info['show']['details'].get('groupShow'):
            startAt = info['show']['details']['groupShow'].get('startAt', '')
        if startAt:
            BJtime = (datetime.strptime(startAt, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=8)).strftime("%m月%d日 %H:%M")
            remark = f"🎫 始于 {BJtime}"
        vod = [{
            "vod_id": id,
            "vod_name": str(info['topic']).strip(), 
            "vod_pic": str(user['avatarUrl']),
            "vod_director": f"{flag}{username}{isLive}",
            "vod_remarks": remark,
            'vod_play_from': 'StripChat',
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
        users = rsp.get('models', [])
        videos = []
        for user in users:
            if not user['isLive']:
                continue
            id = str(user['id'])
            name = str(user['username']).strip()
            stamp = user['snapshotTimestamp']
            country = str(user['country']).strip()
            flag = self.country_code_to_flag(country)
            remark = "🎫" if user['status'] == "groupShow" else ""
            videos.append({
                "vod_id": name,
                "vod_name": f"{flag}{name}",
                "vod_pic": f"https://img.doppiocdn.net/thumbs/{stamp}/{id}",
                "vod_remarks": remark
            })
        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):
        domain = f"https://edge-hls.doppiocdn.net/hls/{id}/master/{id}_auto.m3u8?playlistType=lowLatency"
        self._dbg(f"master m3u8: {domain}")
        resp = self.fetch(domain)
        text = getattr(resp, "text", "") or ""
        self._dbg(f"master status={getattr(resp,'status_code',None)} bytes={len(text)}")
        if getattr(self, "debug", False):
            head = "\n".join(text.splitlines()[:25])
            self._dbg(f"master head:\n{head}")
        lines = text.strip().split('\n') if text else []
        psch, pkey = '', ''
        url = []
        for i, line in enumerate(lines):
            if line.startswith('#EXT-X-MOUFLON:'):
                parts = line.split(':')
                if len(parts) >= 4:
                    psch = parts[2]
                    pkey = parts[3]
            if '#EXT-X-STREAM-INF' in line:
                name_start = line.find('NAME="') + 6
                name_end = line.find('"', name_start)
                qn = line[name_start:name_end]
                # URL在下一行
                if i + 1 >= len(lines):
                    continue
                url_base = lines[i + 1]
                # 组合最终的URL，并加上psch和pkey参数
                full_url = f"{url_base}&psch={psch}&pkey={pkey}"
                proxy_url = f"{self.getProxyUrl()}&url={quote(full_url)}"
                self._dbg(f"variant qn={qn} full={full_url}")
                # 将画质和URL添加到列表中
                url.append(qn)
                url.append(proxy_url)
        result = {}
        result["url"] = url
        result["parse"] = 0
        result["contentType"] = ''
        result["header"] = self.headers
        return result

    def localProxy(self, param):
        url = unquote(param['url'])
        self._dbg(f"proxy fetch: {url}")
        data = self.fetch(url)
        # 兼容部分清晰度被 403 的情况（参考同目录 boyfriend.show.py）
        if getattr(data, "status_code", None) == 403:
            data = self.fetch(re.sub(r'\d+p\d*\.m3u8', '160p_blurred.m3u8', url))
        if data.status_code != 200:
            return [404, "text/plain", ""]
        data = data.text
        # 新老两种 MOUFLON 形式都处理：
        # - FILE: 需要解密 media.mp4
        # - URI: 用 #EXT-X-MOUFLON:URI 后的真实链接替换下一行的 media.mp4 占位符
        if "#EXT-X-MOUFLON:" in data:
            data = self.process_m3u8_content_v2(data)
        # 关键：把 m3u8 内部的相对链接改成绝对链接，否则播放器会相对 proxy:// 去拼导致分片拉取失败/卡顿
        data = self.absolutize_m3u8(url, data)
        return [200, "application/vnd.apple.mpegurl", data]

    def absolutize_m3u8(self, playlist_url: str, m3u8_content: str) -> str:
        """将 m3u8 中的相对 URL 绝对化（以原始 playlist_url 为基准）。"""
        if not m3u8_content:
            return m3u8_content
        out_lines = []
        for line in m3u8_content.splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"):
                out_lines.append(line)
                continue
            # 已是绝对 URL 的不处理
            if raw.startswith(("http://", "https://")):
                out_lines.append(raw)
                continue
            out_lines.append(urljoin(playlist_url, raw))
        return "\n".join(out_lines)

    def process_m3u8_content_v2(self, m3u8_content):
        lines = m3u8_content.strip().split('\n')
        for i, line in enumerate(lines):
            # 形式1：#EXT-X-MOUFLON:FILE:<base64> + 下一行包含 media.mp4（需要解密替换）
            if line.startswith('#EXT-X-MOUFLON:FILE:') and i + 1 < len(lines) and 'media.mp4' in lines[i + 1]:
                encrypted_data = line.split(':', 2)[2].strip()
                decrypted_data = None
                for k in (self.stripchat_key, "Zokee2OhPh9kugh4"):
                    try:
                        decrypted_data = self.decrypt(encrypted_data, k)
                        break
                    except Exception:
                        decrypted_data = None
                # 两种 key 都失败：不替换，避免代理直接报错导致播放卡死
                if decrypted_data:
                    lines[i + 1] = lines[i + 1].replace('media.mp4', decrypted_data)

            # 形式2：#EXT-X-MOUFLON:URI:<真实mp4> + 下一行是 media.mp4 占位符（直接替换为真实链接）
            if line.startswith('#EXT-X-MOUFLON:URI:') and i + 1 < len(lines) and 'media.mp4' in lines[i + 1]:
                real_url = line.split(':', 2)[2].strip()
                nxt = lines[i + 1]
                # 情况A：EXT-X-PART / EXT-X-MAP 等属性里有 URI="...media.mp4"
                if 'URI="' in nxt:
                    lines[i + 1] = re.sub(r'URI="[^"]*media\.mp4"', f'URI="{real_url}"', nxt)
                else:
                    # 情况B：纯 URL 行
                    lines[i + 1] = real_url

        return '\n'.join(lines)

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

    def create_session_with_retry(self, retries=3, backoff_factor=0.3):
        self.session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504]  # 需要重试的状态码
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self, url, **kwargs):
        # 统一使用 Session，便于重试/代理/超时等策略一致
        headers = kwargs.pop("headers", None) or self.headers
        timeout = kwargs.pop("timeout", getattr(self, "timeout", 10))
        return self.session.get(url, headers=headers, timeout=timeout, **kwargs)
