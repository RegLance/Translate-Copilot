"""翻译服务模块 - OpenAI API 封装（支持流式翻译）"""
import hashlib
from typing import Optional, Dict, Generator, Callable
from dataclasses import dataclass
import sys
from pathlib import Path

# 添加父目录到路径以支持相对导入
_parent_dir = Path(__file__).parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

from openai import OpenAI

try:
    from ..config import get_config
    from ..utils.logger import log_warning, log_info, log_translation
except ImportError:
    from config import get_config
    from utils.logger import log_warning, log_info, log_translation


@dataclass
class TranslationResult:
    """翻译结果"""
    original_text: str
    translated_text: str
    source_language: Optional[str] = None
    target_language: str = "中文"
    error: Optional[str] = None


class Translator:
    """翻译服务类"""

    def __init__(self):
        """初始化翻译服务"""
        self._client: Optional[OpenAI] = None
        self._cache: Dict[str, TranslationResult] = {}
        self._init_client()

    def _init_client(self):
        """初始化 OpenAI 客户端"""
        config = get_config()
        api_key = config.get('translator.api_key', '')

        if not api_key:
            log_warning("未配置 OpenAI API Key，请在 config.yaml 中设置")
            self._client = None
            return

        self._client = OpenAI(
            api_key=api_key,
            base_url=config.get('translator.base_url', 'https://api.openai.com/v1'),
            timeout=config.get('translator.timeout', 60),
        )

    def _get_cache_key(self, text: str, target_language: str) -> str:
        """生成缓存键"""
        return hashlib.md5(f"{text}:{target_language}".encode()).hexdigest()

    def _build_prompt(self, text: str, target_language: str) -> str:
        """构建翻译 Prompt"""
        return f"""你是一个专业的翻译助手。请将以下文本翻译成{target_language}。

要求：
1. 如果文本已经是{target_language}，请简要解释其含义或用法
2. 保持原文的风格和语气
3. 对于专业术语，给出准确的翻译
4. 如果是代码或技术内容，保持专业性和准确性
5. 简洁输出，不需要额外的解释

原文: {text}

翻译结果:"""

    def translate_stream(self, text: str, target_language: str = None,
                         on_chunk: Callable[[str], None] = None) -> Generator[str, None, None]:
        """流式翻译文本

        Args:
            text: 待翻译的文本
            target_language: 目标语言
            on_chunk: 每次收到新内容时的回调函数

        Yields:
            str: 翻译结果的文本片段
        """
        if not text or not text.strip():
            yield ""
            return

        text = text.strip()
        if target_language is None:
            target_language = get_config().target_language

        # 检查缓存
        cache_key = self._get_cache_key(text, target_language)
        if cache_key in self._cache:
            cached_result = self._cache[cache_key].translated_text
            yield cached_result
            return

        # 检查客户端
        if self._client is None:
            # 检查是否未配置 API
            config = get_config()
            api_key = config.get('translator.api_key', '')
            base_url = config.get('translator.base_url', '')
            model = config.get('translator.model', '')

            if not api_key:
                yield "[错误: 请先在设置中配置 API Key]"
                return
            if not base_url:
                yield "[错误: 请先在设置中配置 Base URL]"
                return
            if not model:
                yield "[错误: 请先在设置中配置 Model]"
                return

            # 重新初始化客户端
            self._init_client()
            if self._client is None:
                yield "[错误: API 配置无效，请检查设置]"
                return

        try:
            model = get_config().get('translator.model', 'gpt-4o-mini')
            stream = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专业的翻译助手，擅长多种语言的互译。"},
                    {"role": "user", "content": self._build_prompt(text, target_language)}
                ],
                max_tokens=1000,
                temperature=0.3,
                stream=True,  # 启用流式输出
            )

            full_text = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_text += content
                    if on_chunk:
                        on_chunk(content)
                    yield content

            # 存入缓存
            result = TranslationResult(
                original_text=text,
                translated_text=full_text.strip(),
                target_language=target_language
            )
            self._cache[cache_key] = result

        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "401" in error_msg:
                error_msg = "API Key 无效或未配置"
            elif "rate_limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "请求过于频繁，请稍后重试"
            elif "connection" in error_msg.lower():
                error_msg = "网络连接失败"
            else:
                error_msg = f"翻译失败: {error_msg}"

            yield f"[错误: {error_msg}]"

    def translate_sync(self, text: str, target_language: str = None) -> TranslationResult:
        """同步翻译（用于非流式场景）"""
        if not text or not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text="",
                error="文本为空"
            )

        text = text.strip()
        if target_language is None:
            target_language = get_config().target_language

        # 检查缓存
        cache_key = self._get_cache_key(text, target_language)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 检查客户端
        if self._client is None:
            # 检查是否未配置 API
            config = get_config()
            api_key = config.get('translator.api_key', '')
            base_url = config.get('translator.base_url', '')
            model = config.get('translator.model', '')

            if not api_key:
                return TranslationResult(
                    original_text=text,
                    translated_text="",
                    error="请先在设置中配置 API Key",
                    target_language=target_language
                )
            if not base_url:
                return TranslationResult(
                    original_text=text,
                    translated_text="",
                    error="请先在设置中配置 Base URL",
                    target_language=target_language
                )
            if not model:
                return TranslationResult(
                    original_text=text,
                    translated_text="",
                    error="请先在设置中配置 Model",
                    target_language=target_language
                )

            # 重新初始化客户端
            self._init_client()
            if self._client is None:
                return TranslationResult(
                    original_text=text,
                    translated_text="",
                    error="API 配置无效，请检查设置",
                    target_language=target_language
                )

        try:
            model = get_config().get('translator.model', 'gpt-4o-mini')
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专业的翻译助手，擅长多种语言的互译。"},
                    {"role": "user", "content": self._build_prompt(text, target_language)}
                ],
                max_tokens=1000,
                temperature=0.3,
            )

            translated_text = response.choices[0].message.content.strip()

            result = TranslationResult(
                original_text=text,
                translated_text=translated_text,
                target_language=target_language
            )

            # 存入缓存
            self._cache[cache_key] = result

            return result

        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "401" in error_msg:
                error_msg = "API Key 无效或未配置"
            elif "rate_limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "请求过于频繁，请稍后重试"
            elif "connection" in error_msg.lower():
                error_msg = "网络连接失败"

            return TranslationResult(
                original_text=text,
                translated_text="",
                error=error_msg,
                target_language=target_language
            )

    def clear_cache(self):
        """清除翻译缓存"""
        self._cache.clear()

    def reinitialize(self):
        """重新初始化客户端（配置变更后）"""
        self._init_client()


# 全局翻译器实例
_translator_instance: Optional[Translator] = None


def get_translator() -> Translator:
    """获取全局翻译器实例"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = Translator()
    return _translator_instance


def reinitialize_translator():
    """重新初始化翻译器"""
    global _translator_instance
    if _translator_instance is not None:
        _translator_instance.reinitialize()
    else:
        _translator_instance = Translator()