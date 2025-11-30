#!/usr/bin/env python3
"""
定时收集arXiv上特定领域和关键词的论文，并进行总结和语音播报。
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import arxiv
from dateutil import parser
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置参数
CONFIG = {
    "fields": ["physics", "astro-ph"],
    "keywords": ["pulsar", "fast radio burst", "neutron star", "magnetar"],
    "max_results": 10,
    "summary_language": "zh-cn",
    "voice_language": "zh-CN",  # 使用标准的zh-CN格式
    "storage_path": "./arxiv_papers",
    "schedule_interval": 86400,  # 每天运行一次，单位：秒
    # 翻译配置
    "translation": {
        "type": "doubao",  # 可选: "google", "baidu", "doubao"
        # 百度翻译API配置（需要申请）
        "baidu": {
            "app_id": "",
            "app_key": ""
        },
        # 豆包AI配置（需要申请）
        "doubao": {
            "api_key": "",
            "secret_key": ""
        }
    }
}

# 创建存储目录
os.makedirs(CONFIG["storage_path"], exist_ok=True)


class Translator:
    """翻译工具类，支持多种翻译服务。"""
    
    def __init__(self):
        self.translator_type = CONFIG["translation"]["type"]
        self.google_translator = None
        self.baidu_translator = None
        self.doubao_translator = None
    
    def get_google_translator(self):
        """获取Google翻译器。"""
        if self.google_translator is None:
            try:
                from googletrans import Translator
                self.google_translator = Translator()
                logger.info("成功初始化googletrans翻译器")
            except Exception as e:
                logger.error(f"初始化Google翻译器失败: {e}")
                self.google_translator = None
        return self.google_translator
    
    def get_baidu_translator(self):
        """获取百度翻译器。"""
        if self.baidu_translator is None:
            try:
                from baidu_translate_api import BaiduTranslate
                app_id = CONFIG["translation"]["baidu"]["app_id"]
                app_key = CONFIG["translation"]["baidu"]["app_key"]
                
                if not app_id or not app_key:
                    logger.warning("百度翻译API配置不完整")
                    return None
                
                self.baidu_translator = BaiduTranslate(app_id, app_key)
                logger.info("成功初始化百度翻译器")
            except ImportError:
                logger.error("baidu-translate-api未安装")
                self.baidu_translator = None
            except Exception as e:
                logger.error(f"初始化百度翻译器失败: {e}")
                self.baidu_translator = None
        return self.baidu_translator
    
    def get_doubao_translator(self):
        """获取豆包翻译器。"""
        if self.doubao_translator is None:
            try:
                from volcengine.ark.runtime import Chat
                from volcengine.ark.runtime import Message
                
                api_key = CONFIG["translation"]["doubao"]["api_key"]
                secret_key = CONFIG["translation"]["doubao"]["secret_key"]
                
                if not api_key or not secret_key:
                    logger.warning("豆包AI配置不完整")
                    return None
                
                # 豆包AI初始化需要配置环境变量或直接传入
                self.doubao_translator = Chat()
                logger.info("成功初始化豆包翻译器")
            except ImportError:
                logger.error("volcengine-python-sdk未安装")
                self.doubao_translator = None
            except Exception as e:
                logger.error(f"初始化豆包翻译器失败: {e}")
                self.doubao_translator = None
        return self.doubao_translator
    
    def translate(self, text: str, src: str = "en", dest: str = "zh-cn") -> str:
        """将文本从源语言翻译成目标语言。"""
        try:
            # 首先尝试使用豆包AI翻译
            if self.translator_type == "doubao":
                # 使用豆包AI翻译（通过API调用）
                import requests
                import json
                
                api_key = CONFIG["translation"]["doubao"]["api_key"]
                secret_key = CONFIG["translation"]["doubao"]["secret_key"]
                
                if not api_key or not secret_key:
                    logger.warning("豆包AI配置不完整，尝试使用Google翻译")
                else:
                    # 豆包AI API调用
                    url = "https://api.doubao.com/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    }
                    
                    data = {
                        "model": "doubao-pro-128k",
                        "messages": [
                            {"role": "system", "content": "你是一个专业的翻译助手，请将英文翻译成中文，保持准确和流畅。"},
                            {"role": "user", "content": f"将以下英文翻译成中文：{text}"}
                        ]
                    }
                    
                    response = requests.post(url, headers=headers, json=data, timeout=30)
                    response.raise_for_status()
                    
                    result = response.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        translated_text = result["choices"][0]["message"]["content"]
                        logger.info("使用豆包AI翻译成功")
                        return translated_text
            
            # 如果豆包AI不可用或失败，回退到Google翻译
            translator = self.get_google_translator()
            if translator:
                result = translator.translate(text, src=src, dest=dest)
                return result.text
            
            logger.warning("所有翻译器均不可用，返回原文")
            return text
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return text

# 创建全局翻译器实例
translator = Translator()


def build_query(keywords: List[str]) -> str:
    """构建搜索查询字符串。"""
    return " OR ".join(f"\"{keyword}\"" for keyword in keywords)


def build_categories(fields: List[str]) -> List[str]:
    """构建分类列表。"""
    # 扩展领域到具体子分类
    category_map = {
        "physics": ["physics.acc-ph", "physics.app-ph", "physics.atm-clus", "physics.atom-ph",
                    "physics.bio-ph", "physics.chem-ph", "physics.class-ph", "physics.comp-ph",
                    "physics.data-an", "physics.flu-dyn", "physics.gen-ph", "physics.geo-ph",
                    "physics.hist-ph", "physics.ins-det", "physics.med-ph", "physics.optics",
                    "physics.ed-ph", "physics.soc-ph", "physics.plasm-ph", "physics.pop-ph",
                    "physics.space-ph"],
        "astro-ph": ["astro-ph.CO", "astro-ph.EP", "astro-ph.GA", "astro-ph.HE",
                     "astro-ph.IM", "astro-ph.SR"],
    }
    
    categories = []
    for field in fields:
        if field in category_map:
            categories.extend(category_map[field])
        else:
            categories.append(field)
    
    return categories


async def search_papers() -> List[Dict[str, Any]]:
    """搜索特定领域和关键词的论文。"""
    logger.info("开始搜索论文...")
    
    # 构建查询和分类
    query = build_query(CONFIG["keywords"])
    categories = build_categories(CONFIG["fields"])
    
    logger.info(f"搜索查询: {query}")
    logger.info(f"搜索分类: {categories}")
    
    # 创建arxiv客户端
    client = arxiv.Client()
    
    # 设置搜索参数
    search = arxiv.Search(
        query=query,
        max_results=CONFIG["max_results"],
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    
    # 执行搜索
    results = []
    for result in client.results(search):
        # 过滤分类
        if any(cat in result.categories for cat in categories):
            paper = {
                "id": result.get_short_id(),
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "abstract": result.summary,
                "categories": result.categories,
                "published": result.published.isoformat(),
                "url": result.pdf_url,
            }
            results.append(paper)
            
            # 限制结果数量
            if len(results) >= CONFIG["max_results"]:
                break
    
    logger.info(f"搜索完成，找到 {len(results)} 篇论文")
    return results


async def summarize_paper(paper: Dict[str, Any]) -> str:
    """将论文内容总结为包含主要结论的中文，清理LaTeX数学标识符。"""
    # 提取标题和摘要
    title = paper['title']
    abstract = paper['abstract']
    
    # 清理LaTeX数学标识符
    import re
    
    # 移除美元符号包围的数学公式
    title = re.sub(r'\$.*?\$', '', title)
    abstract = re.sub(r'\$.*?\$', '', abstract)
    
    # 移除其他LaTeX标记
    title = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', title)
    abstract = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', abstract)
    
    # 移除多余的空格和换行符
    title = re.sub(r'\s+', ' ', title).strip()
    abstract = re.sub(r'\s+', ' ', abstract).strip()
    
    # 翻译标题和摘要
    logger.info(f"正在翻译论文: {title}")
    
    # 先翻译标题
    translated_title = translator.translate(title)
    
    # 翻译完整摘要，不截断
    translated_abstract = translator.translate(abstract)
    
    # 构建包含主要结论的中文总结
    summary = f"{translated_title}：{translated_abstract}"
    
    # 进一步优化，确保总结流畅
    summary = summary.replace('  ', ' ')
    summary = summary.replace('。。。', '...')
    summary = summary.replace('，，', '，')
    
    logger.info(f"翻译后的中文总结: {summary}")
    return summary


async def text_to_speech(text: str, output_path: str) -> None:
    """将文本转换为语音，使用edge-tts。"""
    logger.info(f"正在将文本转换为语音: {output_path}")
    
    try:
        # 尝试使用edge-tts（更好的语音质量）
        import edge_tts
        
        # 使用更自然的中文语音
        voice = "zh-CN-XiaoxiaoNeural"  # 微软的晓晓语音
        
        # 创建edge-tts通信对象
        communicate = edge_tts.Communicate(text, voice)
        
        # 生成语音文件
        await communicate.save(output_path)
        
        logger.info(f"使用edge-tts生成语音文件成功: {output_path}")
    except ImportError:
        # 如果edge-tts不可用，回退到gtts
        logger.warning("edge-tts未安装，回退到gtts")
        from gtts import gTTS
        
        tts = gTTS(text=text, lang=CONFIG["voice_language"])
        tts.save(output_path)
        logger.info(f"使用gtts生成语音文件成功: {output_path}")
    except Exception as e:
        logger.error(f"生成语音失败: {e}")
        raise


async def play_speech(file_path: str) -> None:
    """播放语音文件，确保完整播放。"""
    logger.info(f"正在播放语音: {file_path}")
    
    try:
        # 尝试使用pygame播放，这是最可靠的方法
        import pygame
        import time
        
        # 初始化pygame
        pygame.mixer.init()
        
        # 加载并播放语音文件
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        
        # 等待播放完成
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
            await asyncio.sleep(0.1)  # 允许其他任务运行
        
        # 清理资源
        pygame.mixer.quit()
        logger.info(f"语音播放完成: {file_path}")
    except Exception as e:
        logger.error(f"使用pygame播放语音失败: {e}")
        
        try:
            import subprocess
            import os
            import time
            
            # 获取文件大小，估计播放时间
            file_size = os.path.getsize(file_path)  # 字节
            
            # 估计播放时间（MP3格式大约1MB/分钟，增加20%的缓冲时间）
            estimated_time = max(10, int(file_size / (1024 * 1024) * 60 * 1.2))  # 最小10秒，增加20%缓冲
            logger.info(f"估计语音播放时间: {estimated_time}秒")
            
            # 使用系统默认播放器打开文件
            if os.name == 'nt':  # Windows
                subprocess.Popen(['start', '', file_path], shell=True)
            elif os.name == 'posix':  # macOS or Linux
                subprocess.Popen(['open', file_path])
            
            # 等待足够的时间让语音播放完成
            await asyncio.sleep(estimated_time)
            logger.info(f"语音播放完成: {file_path}")
        except Exception as e2:
            logger.error(f"播放语音失败: {e2}")
            # 回退到简单方法
            if os.name == 'nt':
                os.system(f"start {file_path}")
            else:
                os.system(f"open {file_path}")
            await asyncio.sleep(15)  # 增加等待时间到15秒


async def process_papers(papers: List[Dict[str, Any]]) -> None:
    """处理搜索到的论文。"""
    for i, paper in enumerate(papers):
        logger.info(f"处理第 {i+1} 篇论文: {paper['title']}")
        
        # 总结论文
        summary = await summarize_paper(paper)
        logger.info(f"论文总结: {summary}")
        
        # 保存总结
        summary_file = os.path.join(CONFIG["storage_path"], f"{paper['id']}_summary.txt")
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary)
        
        # 转换为语音
        speech_file = os.path.join(CONFIG["storage_path"], f"{paper['id']}_summary.mp3")
        await text_to_speech(summary, speech_file)
        
        # 播放语音
        await play_speech(speech_file)
        
        # 等待一段时间再处理下一篇
        await asyncio.sleep(2)


async def main() -> None:
    """主函数。"""
    logger.info("启动arXiv论文收集和播报服务")
    
    while True:
        try:
            # 搜索论文
            papers = await search_papers()
            
            if papers:
                # 处理论文
                await process_papers(papers)
            else:
                logger.info("没有找到符合条件的论文")
                # 生成提示语音
                no_papers_text = "没有找到符合条件的论文。"
                no_papers_file = os.path.join(CONFIG["storage_path"], "no_papers.mp3")
                await text_to_speech(no_papers_text, no_papers_file)
                await play_speech(no_papers_file)
            
            # 等待下一次运行
            logger.info(f"等待 {CONFIG['schedule_interval']} 秒后再次运行")
            await asyncio.sleep(CONFIG["schedule_interval"])
            
        except Exception as e:
            logger.error(f"发生错误: {e}")
            # 等待一段时间后重试
            await asyncio.sleep(3600)  # 1小时后重试


if __name__ == "__main__":
    asyncio.run(main())
