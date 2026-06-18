import aiohttp
import json
import os
import random
from typing import List, Dict, Any, Optional
import urllib.parse
import traceback

TRIGGHT_KEYWORD = "Any"  # 我们需要处理多种命令，所以使用 Any

HELP_MESSAGE = "【Meme列表】查看表情列表\n【表情名@人】制作表情\n【Meme搜索+词】搜索表情\n【表情名+详情】查看用法\n【设置/删除主人+QQ】管理主人\n【点歌+歌名】搜索并点歌\n【听+序号】播放搜索到的歌曲\n提示：大部分表情需要@人，可以使用“娱乐菜单”查看全部命令"

# 配置
PLUGIN_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(PLUGIN_DIR, "data")
MEME_API_URL = "http://datukuai.top:2233"
MUSIC_API_URL = "https://a.aa.cab"
MAX_FILE_SIZE = 10 * 1024 * 1024
ENABLE_MASTER_PROTECT = True
OWNER_QQS = [] # 在需要的地方加载

# 缓存
music_cache = {}  # user_id -> dict
bq_data = {}
meme_infos = {}
meme_keymap = {}
meme_list_cache = None

# 初始化
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def load_bq_json():
    global bq_data, meme_infos, meme_keymap
    try:
        bq_path = os.path.join(PLUGIN_DIR, "bq.json")
        if os.path.exists(bq_path):
            with open(bq_path, "r", encoding="utf-8") as f:
                bq_data = json.load(f)

            for key, data in bq_data.items():
                meme_infos[key] = data
                for kw in data.get("keywords", []):
                    meme_keymap[kw] = key
    except Exception as e:
        print(f"[Play Plugin] Error loading bq.json: {e}")

load_bq_json()

async def download_image(url: str) -> Optional[bytes]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        print(f"Download image error: {e}")
    return None

def get_avatar_url(user_id: str) -> str:
    return f"https://q1.qlogo.cn/g?b=qq&s=160&nk={user_id}"

async def search_music(keyword: str) -> Optional[List[Dict]]:
    try:
        encoded = urllib.parse.quote(keyword)
        url = f"{MUSIC_API_URL}/qq.music?msg={encoded}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("data"):
                        return data["data"][:10]
    except Exception as e:
        print(f"Search music error: {e}")
    return None

async def get_music_url(keyword: str, index: int) -> Optional[str]:
    try:
        encoded = urllib.parse.quote(keyword)
        url = f"{MUSIC_API_URL}/qq.music?msg={encoded}&n={index}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("data") and data["data"].get("music"):
                        return data["data"]["music"]
    except Exception as e:
        print(f"Get music error: {e}")
    return None

def get_meme_list_image_base64() -> Optional[str]:
    global meme_list_cache
    if meme_list_cache:
        return meme_list_cache

    meme_list_path = os.path.join(PLUGIN_DIR, "meme-list.png")
    if os.path.exists(meme_list_path):
        try:
            import base64
            with open(meme_list_path, "rb") as f:
                meme_list_cache = base64.b64encode(f.read()).decode()
            return meme_list_cache
        except:
            pass
    return None

async def generate_meme(code: str, images_data: List[bytes], texts: List[str], args: str = "") -> Optional[bytes]:
    try:
        url = f"{MEME_API_URL}/memes/{code}/"
        data = aiohttp.FormData()

        for i, img in enumerate(images_data):
            data.add_field('images', img, filename=f'img{i}.jpg', content_type='image/jpeg')

        for text in texts:
            data.add_field('texts', text)

        if args:
            data.add_field('args', args)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=15) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    err_text = await response.text()
                    print(f"Meme generation failed: {response.status} - {err_text}")
    except Exception as e:
        print(f"Generate meme error: {e}")
    return None

def find_longest_matching_key(msg: str) -> Optional[str]:
    keys = [k for k in meme_keymap.keys() if msg.startswith(k)]
    if keys:
        keys.sort(key=len, reverse=True)
        return keys[0]
    return None


def extract_message_text(event, fallback: str = "") -> str:
    text_parts = []
    if getattr(event, 'message', None):
        for seg in event.message:
            if getattr(seg, '__class__', None).__name__ == 'Text':
                text = getattr(seg, 'text', None) or getattr(seg, 'content', None)
                if text:
                    text_parts.append(str(text))
            elif isinstance(seg, dict) and seg.get('type') == 'text':
                data = seg.get('data', {})
                text = data.get('text') or data.get('content')
                if text:
                    text_parts.append(str(text))
    return "".join(text_parts).strip() or str(fallback).strip()

def get_meme_detail(code: str) -> str:
    d = meme_infos.get(code)
    if not d:
        return "未找到该表情信息"

    keywords = "、".join(d.get('keywords', []))
    min_images = d.get('params_type', {}).get('min_images', 0)
    max_images = d.get('params_type', {}).get('max_images', 0)
    min_texts = d.get('params_type', {}).get('min_texts', 0)
    max_texts = d.get('params_type', {}).get('max_texts', 0)

    ins = f"【代码】{code}\n【名称】{keywords}\n【图片】{min_images}-{max_images}\n【文本】{min_texts}-{max_texts}"
    if d.get('params_type', {}).get('args_type', {}).get('parser_options'):
        ins += "\n【参数】支持额外参数"
    return ins

async def on_message(event, actions, Manager, Segments, user_message="", is_group=False, **kwargs):
    try:
        user_id = str(event.user_id)
        msg = extract_message_text(event, user_message)

        # 提取CQ码信息
        # 简化的实现，依赖于传入的文本

        # 1. 娱乐菜单
        if msg in ["娱乐菜单", "play菜单", "功能菜单"]:
            menu_text = "🎮 Play 娱乐插件菜单\n\n📸 表情包功能\n• meme列表 - 查看表情列表\n• 表情名 - 制作表情（可@人或引用图片）\n• 表情名+详情 - 查看表情用法\n• meme搜索+关键词 - 搜索表情\n• 随机meme - 随机生成表情\n\n🎵 点歌功能\n• 点歌+歌名 - 搜索歌曲\n• 听+序号 - 播放搜索到的歌曲\n\n💡 提示：大部分表情需要@人，例如：摸@小明"
            await actions.send(
                group_id=event.group_id if is_group else None,
                user_id=event.user_id if not is_group else None,
                message=Manager.Message(Segments.Text(menu_text))
            )
            return True

        # 2. 音乐点歌
        if msg.startswith("点歌 "):
            keyword = msg[3:].strip()
            if not keyword:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("请输入要搜索的歌曲名，如：点歌 晴天"))
                )
                return True

            songs = await search_music(keyword)
            if not songs:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("未找到相关歌曲或请求超时"))
                )
                return True

            music_cache[user_id] = {"songs": songs, "keyword": keyword}

            reply_msg = f"🎵 点歌结果：{keyword}\n发送\"听+序号\"播放，如：听1\n"
            for i, song in enumerate(songs):
                song_name = song.get("song", "未知歌名").replace("&", "").replace("<", "").replace(">", "")
                singer = song.get("singer", "未知歌手").replace("&", "").replace("<", "").replace(">", "")
                reply_msg += f"{i+1}. {song_name} - {singer}\n"

            reply_msg += '💡 提示：发送"听1"到"听10"播放对应歌曲'

            await actions.send(
                group_id=event.group_id if is_group else None,
                user_id=event.user_id if not is_group else None,
                message=Manager.Message(Segments.Text(reply_msg))
            )
            return True

        if msg.startswith("听") and msg[1:].isdigit():
            idx = int(msg[1:])
            cache = music_cache.get(user_id)
            if not cache or not cache.get("songs"):
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text('请先使用"点歌+歌名"搜索歌曲'))
                )
                return True

            songs = cache["songs"]
            if idx < 1 or idx > len(songs):
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text(f"请输入1-{len(songs)}之间的序号"))
                )
                return True

            music_url = await get_music_url(cache["keyword"], idx)
            if not music_url:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("未获取到歌曲链接，请换一首歌尝试"))
                )
                return True

            await actions.send(
                group_id=event.group_id if is_group else None,
                user_id=event.user_id if not is_group else None,
                message=Manager.Message(Segments.Record(music_url))
            )
            return True

        # 3. Meme列表与搜索
        if msg in ["meme列表", "memes列表", "表情包列表", "Meme列表"]:
            img_b64 = get_meme_list_image_base64()
            if img_b64:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Image(f"base64://{img_b64}"))
                )
            else:
                kws = [f"【{k}】" for k in list(meme_keymap.keys())[:30]]
                kws_str = " ".join(kws)
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text(f"【Meme列表】共 {len(meme_keymap)} 个\n\n{kws_str} ...\n\n发送【meme搜索+词】搜索更多"))
                )
            return True

        if msg.startswith("meme搜索") or msg.startswith("表情包搜索") or msg.startswith("Meme搜索"):
            s = msg.replace("meme搜索", "").replace("表情包搜索", "").replace("Meme搜索", "").strip()
            if not s:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("请输入关键词"))
                )
                return True

            hits = [k for k in meme_keymap.keys() if s in k]
            if not hits:
                reply = "搜索结果：\n无结果"
            else:
                lines = [f"{i+1}. {k}" for i, k in enumerate(hits[:20])]
                reply = "搜索结果：\n" + "\n".join(lines)
                if len(hits) > 20:
                    reply += f"\n...共{len(hits)}个"

            await actions.send(
                group_id=event.group_id if is_group else None,
                user_id=event.user_id if not is_group else None,
                message=Manager.Message(Segments.Text(reply))
            )
            return True

        if msg in ["随机meme", "随机memes", "随机表情包", "随机Meme"]:
            # 找到只需要1张图0段文字的表情
            valid_keys = []
            for code, info in meme_infos.items():
                if info.get('params_type', {}).get('min_images') == 1 and info.get('params_type', {}).get('min_texts') == 0:
                    if info.get('keywords'):
                        valid_keys.append(info['keywords'][0])

            if valid_keys:
                kw = random.choice(valid_keys)
                msg = kw  # 继续执行meme生成逻辑
            else:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("暂无可用随机meme"))
                )
                return True

        # 4. Meme生成
        target = find_longest_matching_key(msg)
        if target:
            code = meme_keymap.get(target)
            info = meme_infos.get(code)
            if not info:
                return False

            # 解析消息
            text1 = msg[len(target):]
            if text1.strip() in ["详情", "帮助"]:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text(get_meme_detail(code)))
                )
                return True

            parts = text1.split("#")
            text = parts[0].strip()
            args = parts[1] if len(parts) > 1 else ""

            # 解析图片和at
            # 注意：在XcBot中，我们需要通过原消息内容或事件分析at谁
            # 这里简化处理，通过纯文本查找是否有 @，或者如果使用了框架自带的提取能力

            at_qQs = []
            reply_msg_id = None
            if getattr(event, 'message', None):
                for seg in event.message:
                    # 获取引用消息的ID
                    if getattr(seg, '__class__', None).__name__ == 'Reply' and getattr(seg, 'id', None):
                        reply_msg_id = seg.id

                    # Fix: segment object might be Segments.Text which doesn't have 'type' attribute but uses isinstance
                    # In Hyper architecture, segments might not have a 'type' attribute directly like in some other frameworks
                    # We check if it's an At segment or has type attribute
                    if hasattr(seg, 'type') and seg.type == 'at' and getattr(seg.data, 'qq', None) and seg.data.qq != 'all':
                        at_qQs.append({'qq': str(seg.data.qq), 'text': getattr(seg.data, 'name', '') or ''})
                    # Alternative check based on Hyper framework structure
                    elif getattr(seg, '__class__', None).__name__ == 'At' and getattr(seg, 'qq', None) and seg.qq != 'all':
                         at_qQs.append({'qq': str(seg.qq), 'text': getattr(seg, 'name', '') or ''})

            # 解析引用消息里的图片和@信息
            reply_images = []
            if reply_msg_id:
                try:
                    content = await actions.get_msg(reply_msg_id)
                    raw_data = None
                    if hasattr(content, 'data') and content.data is not None:
                        raw_data = getattr(content.data, 'raw', None)
                    if raw_data is None and isinstance(content, dict):
                        raw_data = content

                    if raw_data and isinstance(raw_data, dict):
                        msg_data = raw_data.get('message', [])

                        if isinstance(msg_data, list):
                            for seg in msg_data:
                                if isinstance(seg, dict) and seg.get('type') == 'image':
                                    url = seg.get('data', {}).get('url')
                                    if url:
                                        reply_images.append(url)
                                elif hasattr(seg, 'type') and getattr(seg, 'type', None) == 'image':
                                    url = getattr(seg, 'url', None) or (getattr(seg, 'file', None) if str(getattr(seg, 'file', '')).startswith('http') else None)
                                    if url:
                                        reply_images.append(url)
                except Exception as e:
                    print(f"解析引用消息失败: {e}")

            max_images = info.get('params_type', {}).get('max_images', 0)
            min_images = info.get('params_type', {}).get('min_images', 0)
            max_texts = info.get('params_type', {}).get('max_texts', 0)
            min_texts = info.get('params_type', {}).get('min_texts', 0)

            imgs = []
            if max_images > 0:
                # 原版逻辑：先取引用图；只有完全没有图片时，才用 @ 头像
                if reply_images:
                    imgs.extend(reply_images)

                if not imgs and at_qQs:
                    imgs = [get_avatar_url(at['qq']) for at in at_qQs]

                if not imgs and min_images > 0:
                    imgs.append(get_avatar_url(user_id))

                if len(imgs) < min_images and get_avatar_url(user_id) not in imgs:
                    imgs.insert(0, get_avatar_url(user_id))

                imgs = imgs[:max_images]

            texts = []
            if text and max_texts == 0:
                return False
            elif not text and min_texts > 0:
                # 尝试使用at人的名字或发件人名字
                name = "用户"
                if at_qQs and at_qQs[0].get('text'):
                    name = at_qQs[0]['text'].replace('@', '').strip()
                elif getattr(event, 'sender', None):
                    name = getattr(event.sender, 'card', None) or getattr(event.sender, 'nickname', None) or "用户"
                texts.append(name)
            elif text:
                texts = text.split("/")[:max_texts]

            if len(texts) < min_texts:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text(f"需要{min_texts}个文本，用/隔开"))
                )
                return True

            if max_texts > 0 and not texts:
                name = "用户"
                if at_qQs and at_qQs[0].get('text'):
                    name = at_qQs[0]['text'].replace('@', '').strip()
                elif getattr(event, 'sender', None):
                    name = getattr(event.sender, 'card', None) or getattr(event.sender, 'nickname', None) or "用户"
                texts.append(name)

            # 准备args对象
            user_infos = []
            if not at_qQs:
                name = "用户"
                gender = "unknown"
                if getattr(event, 'sender', None):
                    name = getattr(event.sender, 'card', None) or getattr(event.sender, 'nickname', None) or "用户"
                    gender = getattr(event.sender, 'sex', 'unknown')
                user_infos.append({"name": name, "gender": gender})
            else:
                for at in at_qQs:
                    user_infos.append({"name": at['text'].replace('@', ''), "gender": "unknown"})

            args_obj = {"user_infos": user_infos}
            # 忽略复杂参数解析，使用默认值

            buffers = []
            for url in imgs:
                b = await download_image(url)
                if b:
                    buffers.append(b)

            if min_images > 0 and not buffers:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text("图片下载失败"))
                )
                return True

            # 发送生成中提示(如果需要)

            # 生成meme
            result = await generate_meme(code, buffers, texts, json.dumps(args_obj))

            if result:
                import base64
                b64 = base64.b64encode(result).decode()
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Image(f"base64://{b64}"))
                )
            else:
                await actions.send(
                    group_id=event.group_id if is_group else None,
                    user_id=event.user_id if not is_group else None,
                    message=Manager.Message(Segments.Text(f"表情生成失败：{code}"))
                )

            return True

        return False

    except Exception as e:
        traceback.print_exc()
        print(f"Play plugin error: {e}")
        return False
