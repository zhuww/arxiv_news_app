#!/usr/bin/env python3
"""
ArXiv论文新闻播报软件
每天定时收集特定领域和关键词的论文，并进行语音播报
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import arxiv
from dateutil import parser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

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
    "schedule_interval": 7200,  # 每两小时运行一次，单位：秒
    "reminder_start_time": 10,  # 开始提醒时间（小时）
    "reminder_end_time": 18,  # 结束提醒时间（小时）
    "favorite_path": "./favorites",  # 收藏目录
    "translation": {
        "type": "google",  # 可选: "google", "baidu", "doubao"
        "baidu": {
            "app_id": "",
            "app_key": ""
        },
        "doubao": {
            "api_key": "",
            "secret_key": ""
        }
    }
}

# 创建存储目录
os.makedirs(CONFIG["storage_path"], exist_ok=True)
os.makedirs(CONFIG["favorite_path"], exist_ok=True)


class Translator:
    """翻译工具类，支持多种翻译服务。"""
    
    def __init__(self):
        self.translator_type = CONFIG["translation"]["type"]
        self.google_translator = None
    
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
    
    def translate(self, text: str, src: str = "en", dest: str = "zh-cn") -> str:
        """将文本从源语言翻译成目标语言。"""
        try:
            # 默认使用Google翻译
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


class ArxivNewsApp:
    """ArXiv论文新闻播报软件主类。"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ArXiv论文新闻播报")
        self.root.geometry("800x600")
        
        # 设置窗口背景色
        self.root.configure(bg="#f0f8ff")
        
        # 配置ttk样式
        self.setup_styles()
        
        # 状态变量
        self.reminder_enabled = tk.BooleanVar(value=True)
        self.skip_today = False
        self.current_papers = []
        self.current_paper_index = 0
        self.is_playing = False
        self.favorites = []
        
        # 加载收藏列表
        self.load_favorites()
        
        # 创建主界面
        self.create_main_interface()
        
        # 启动定时提醒线程
        self.reminder_thread = threading.Thread(target=self.reminder_loop, daemon=True)
        self.reminder_thread.start()
        
        # 测试：立即运行一次搜索和提醒
        # self.test_immediate_run()  # 注释掉，因为该方法不存在
        
        # 将程序添加到Windows自动运行列表
        self.add_to_auto_start()
        
    def setup_styles(self):
        """配置ttk样式，使其更加现代和卡通化。"""
        style = ttk.Style()
        
        # 设置主题
        style.theme_use("clam")  # 使用clam主题作为基础
        
        # 配置主窗口样式
        style.configure(".", 
                       background="#f0f8ff",
                       foreground="#333333",
                       font=("Arial", 10))
        
        # 配置标签样式
        style.configure("TLabel", 
                       background="#f0f8ff",
                       foreground="#333333",
                       font=("Arial", 10))
        
        # 配置按钮样式
        style.configure("TButton",
                       background="#4a90e2",
                       foreground="white",
                       font=("Arial", 10, "bold"),
                       padding=10,
                       borderwidth=0,
                       relief=tk.FLAT)
        
        style.map("TButton",
                 background=[("active", "#357abd"), ("disabled", "#cccccc")],
                 foreground=[("disabled", "#999999")])
        
        # 配置强调按钮样式
        style.configure("Accent.TButton",
                       background="#3498db",
                       foreground="white",
                       font=("Arial", 10, "bold"),
                       padding=10,
                       borderwidth=0,
                       relief=tk.FLAT)
        
        style.map("Accent.TButton",
                 background=[("active", "#2980b9"), ("disabled", "#cccccc")],
                 foreground=[("disabled", "#999999")])
        
        # 配置成功按钮样式
        style.configure("Success.TButton",
                       background="#2ecc71",
                       foreground="white",
                       font=("Arial", 10, "bold"),
                       padding=10,
                       borderwidth=0,
                       relief=tk.FLAT)
        
        style.map("Success.TButton",
                 background=[("active", "#27ae60"), ("disabled", "#cccccc")],
                 foreground=[("disabled", "#999999")])
        
        # 配置危险按钮样式
        style.configure("Danger.TButton",
                       background="#e74c3c",
                       foreground="white",
                       font=("Arial", 10, "bold"),
                       padding=10,
                       borderwidth=0,
                       relief=tk.FLAT)
        
        style.map("Danger.TButton",
                 background=[("active", "#c0392b"), ("disabled", "#cccccc")],
                 foreground=[("disabled", "#999999")])
        
        # 配置标签页样式
        style.configure("TNotebook",
                       background="#f0f8ff",
                       foreground="#333333",
                       borderwidth=0)
        
        style.configure("TNotebook.Tab",
                       background="#e0f0ff",
                       foreground="#333333",
                       padding=[15, 10],
                       font=("Arial", 10, "bold"))
        
        style.map("TNotebook.Tab",
                 background=[("active", "#4a90e2"), ("selected", "#4a90e2")],
                 foreground=[("active", "white"), ("selected", "white")])
        
        # 配置标签框架样式
        style.configure("TLabelframe",
                       background="#f0f8ff",
                       foreground="#333333",
                       borderwidth=2,
                       relief=tk.GROOVE)
        
        style.configure("TLabelframe.Label",
                       background="#f0f8ff",
                       foreground="#333333",
                       font=("Arial", 11, "bold"),
                       padding=5)
        
        # 配置树视图样式
        style.configure("Treeview",
                       background="white",
                       foreground="#333333",
                       rowheight=25,
                       fieldbackground="white",
                       font=("Arial", 9))
        
        style.configure("Treeview.Heading",
                       background="#4a90e2",
                       foreground="white",
                       font=("Arial", 10, "bold"),
                       padding=10)
        
        style.map("Treeview.Heading",
                 background=[("active", "#357abd")])
        
        style.configure("Treeview.Cell",
                       padding=5)
        
        # 配置滚动条样式
        style.configure("Vertical.TScrollbar",
                       background="#e0e0e0",
                       troughcolor="#f0f0f0",
                       borderwidth=1,
                       relief=tk.FLAT)
        
        style.map("Vertical.TScrollbar",
                 background=[("active", "#4a90e2")])
        
        style.configure("Horizontal.TScrollbar",
                       background="#e0e0e0",
                       troughcolor="#f0f0f0",
                       borderwidth=1,
                       relief=tk.FLAT)
        
        style.map("Horizontal.TScrollbar",
                 background=[("active", "#4a90e2")])
        
        # 配置复选框样式
        style.configure("TCheckbutton",
                       background="#f0f8ff",
                       foreground="#333333",
                       font=("Arial", 10))
        
        style.map("TCheckbutton",
                 background=[("active", "#f0f8ff")])
        
    def create_main_interface(self):
        """创建主界面。"""
        # 创建标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 主页面
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="主页面")
        
        # 收藏页面
        self.favorite_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.favorite_frame, text="收藏列表")
        
        # 配置页面
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="配置")
        
        # 关于页面
        self.about_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.about_frame, text="关于")
        
        # 填充主页面
        self.fill_main_frame()
        
        # 填充收藏页面
        self.fill_favorite_frame()
        
        # 填充配置页面
        self.fill_config_frame()
        
        # 填充关于页面
        self.fill_about_frame()
        
        # 将程序添加到Windows自动运行列表
        self.add_to_auto_start()
        
    def fill_main_frame(self):
        """填充主页面内容，添加卡通元素和丰富的颜色。"""
        # 创建欢迎标签
        welcome_label = ttk.Label(self.main_frame, text="🚀 ArXiv论文新闻播报", font=("Arial", 18, "bold"), foreground="#4a90e2")
        welcome_label.pack(pady=20)
        
        # 创建装饰性标签
        decoration_label = ttk.Label(self.main_frame, text="🔍 探索最新的天体物理研究 🌟", font=("Arial", 12, "italic"), foreground="#4a90e2")
        decoration_label.pack(pady=10)
        
        # 创建状态标签
        self.status_label = ttk.Label(self.main_frame, text="⏳ 等待提醒...", font=("Arial", 12, "bold"), foreground="#333333")
        self.status_label.pack(pady=15)
        
        # 添加卡通装饰
        space_label = ttk.Label(self.main_frame, text="🌌 宇宙浩瀚，知识无限 🌠", font=("Arial", 11, "italic"), foreground="#9b59b6")
        space_label.pack(pady=5)
        
        # 创建控制按钮
        control_frame = ttk.Frame(self.main_frame, style="Card.TFrame")
        control_frame.pack(pady=25, padx=50, fill=tk.X)
        
        # 立即检查按钮
        check_btn = ttk.Button(control_frame, text="🔍 立即检查新论文", command=self.check_new_papers, style="Accent.TButton")
        check_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 播放按钮
        play_btn = ttk.Button(control_frame, text="▶️ 播放最新论文", command=self.play_latest_papers, style="Success.TButton")
        play_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 停止按钮
        stop_btn = ttk.Button(control_frame, text="⏹️ 停止播放", command=self.stop_playback, style="Danger.TButton")
        stop_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 创建提醒设置
        reminder_frame = ttk.LabelFrame(self.main_frame, text="⏰ 提醒设置", style="Decorative.TLabelframe")
        reminder_frame.pack(fill=tk.X, padx=50, pady=15)
        
        reminder_check = ttk.Checkbutton(reminder_frame, text="✅ 启用定时提醒", variable=self.reminder_enabled)
        reminder_check.pack(padx=10, pady=10, anchor=tk.W)
        
        reminder_info = ttk.Label(reminder_frame, text="📅 周一至周五 10:00-18:00，每两小时提醒一次")
        reminder_info.pack(padx=10, pady=5, anchor=tk.W)
        
        # 添加当前时间显示
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label = ttk.Label(self.main_frame, text=f"🕒 当前时间: {current_time}", font=("Arial", 10, "italic"), foreground="#666666")
        self.time_label.pack(pady=10)
        
        # 更新时间的函数
        def update_time():
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.time_label.config(text=f"🕒 当前时间: {current_time}")
            self.root.after(1000, update_time)
        
        # 启动时间更新
        update_time()
        
        # 添加卡通装饰
        cartoon_label = ttk.Label(self.main_frame, text="🎉 让科学探索变得更有趣！", font=("Arial", 14, "bold"), foreground="#ff6b6b")
        cartoon_label.pack(pady=25)
        
        # 添加功能介绍
        features_frame = ttk.LabelFrame(self.main_frame, text="✨ 主要功能", style="Decorative.TLabelframe")
        features_frame.pack(fill=tk.X, padx=50, pady=10)
        
        features = [
            "📚 自动收集arXiv论文",
            "🔤 智能翻译摘要",
            "🎧 自然语音播报",
            "❤️ 一键收藏功能",
            "⏰ 定时提醒机制",
            "📱 现代化卡通界面"
        ]
        
        for feature in features:
            feature_label = ttk.Label(features_frame, text=feature, font=("Arial", 10))
            feature_label.pack(padx=20, pady=5, anchor=tk.W)
        
    def open_play_window(self, paper):
        """打开播放窗口，添加卡通元素和丰富的颜色。"""
        # 创建播放窗口
        play_window = tk.Toplevel(self.root)
        play_window.title("🎧 论文播放")
        play_window.geometry("900x700")
        play_window.configure(bg="#f0f8ff")
        
        # 设置窗口样式
        style = ttk.Style()
        style.configure("PlayWindow.TFrame", background="#f0f8ff")
        
        # 创建标题标签
        title_label = ttk.Label(play_window, text=paper["title"], font=("Arial", 14, "bold"), wraplength=850, foreground="#4a90e2")
        title_label.pack(pady=20, padx=20, anchor=tk.W)
        
        # 创建作者标签
        authors = ", ".join(paper["authors"])[:100] + "..." if len(", ".join(paper["authors"])) > 100 else ", ".join(paper["authors"])
        author_label = ttk.Label(play_window, text=f"👤 作者: {authors}", font=("Arial", 11, "italic"))
        author_label.pack(pady=5, padx=20, anchor=tk.W)
        
        # 创建摘要滚动文本
        abstract_frame = ttk.LabelFrame(play_window, text="📝 摘要", style="Decorative.TLabelframe")
        abstract_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        abstract_text = scrolledtext.ScrolledText(abstract_frame, wrap=tk.WORD, font=("Arial", 11), bg="white", fg="#333333", relief=tk.FLAT, bd=0)
        abstract_text.insert(tk.END, paper["abstract"])
        abstract_text.config(state=tk.DISABLED)
        abstract_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建控制按钮
        control_frame = ttk.Frame(play_window, style="Card.TFrame")
        control_frame.pack(pady=20, padx=20, fill=tk.X)
        
        # 收藏按钮
        favorite_btn = ttk.Button(control_frame, text="❤️ 收藏", command=lambda: self.favorite_paper(paper, play_window))
        favorite_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 下一篇按钮
        def next_paper():
            """下一篇论文处理函数。"""
            self.current_paper_index += 1
            play_window.destroy()
            self.play_next_paper()
        
        next_btn = ttk.Button(control_frame, text="⏭️ 下一篇", command=next_paper)
        next_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 停止按钮
        stop_btn = ttk.Button(control_frame, text="⏹️ 停止", command=lambda: [self.stop_playback(), play_window.destroy()])
        stop_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 开始播放语音
        self.play_paper_speech(paper)
        
    def show_reminder_window(self):
        """显示提醒窗口，添加卡通元素和丰富的颜色。"""
        # 创建提醒窗口
        reminder_window = tk.Toplevel(self.root)
        reminder_window.title("🔔 新论文提醒")
        reminder_window.geometry("500x300")
        reminder_window.configure(bg="#f0f8ff")
        reminder_window.attributes("-topmost", True)  # 置顶显示
        
        # 创建提醒图标
        reminder_icon = ttk.Label(reminder_window, text="✨", font=("Arial", 48))
        reminder_icon.pack(pady=20)
        
        # 创建提醒消息
        reminder_label = ttk.Label(reminder_window, text=f"🎉 发现 {len(self.current_papers)} 篇新论文，是否听取？", 
                                 font=("Arial", 14, "bold"), wraplength=400)
        reminder_label.pack(pady=10)
        
        # 创建按钮框架
        btn_frame = ttk.Frame(reminder_window, style="Card.TFrame")
        btn_frame.pack(pady=30, padx=50, fill=tk.X)
        
        # 选项1：听取
        listen_btn = ttk.Button(btn_frame, text="▶️ 听取", command=lambda: [reminder_window.destroy(), self.play_latest_papers()])
        listen_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 选项2：跳过提醒
        skip_btn = ttk.Button(btn_frame, text="⏭️ 跳过提醒", command=reminder_window.destroy)
        skip_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 选项3：跳过今天
        skip_today_btn = ttk.Button(btn_frame, text="📅 跳过今天", command=lambda: [reminder_window.destroy(), setattr(self, "skip_today", True)])
        skip_today_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
    def fill_favorite_frame(self):
        """填充收藏页面内容。"""
        # 创建收藏列表（三列：标题、作者、年份）
        self.favorite_tree = ttk.Treeview(self.favorite_frame, 
                                         columns=("title", "author", "year"), 
                                         show="headings")
        
        # 设置列标题
        self.favorite_tree.heading("title", text="论文标题")
        self.favorite_tree.heading("author", text="第一作者")
        self.favorite_tree.heading("year", text="年份")
        
        # 设置列宽
        self.favorite_tree.column("title", width=500)
        self.favorite_tree.column("author", width=200)
        self.favorite_tree.column("year", width=100)
        
        self.favorite_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建查看按钮
        view_btn = ttk.Button(self.favorite_frame, text="查看详情", command=self.view_favorite)
        view_btn.pack(side=tk.LEFT, padx=10, pady=10)
        
        # 创建删除按钮
        delete_btn = ttk.Button(self.favorite_frame, text="删除收藏", command=self.delete_favorite)
        delete_btn.pack(side=tk.LEFT, padx=10, pady=10)
        
        # 更新收藏列表
        self.update_favorite_list()
        
    def fill_config_frame(self):
        """填充配置页面内容，添加卡通元素和丰富的颜色。"""
        # 添加卡通装饰
        decor_label = ttk.Label(self.config_frame, text="⚙️ 配置中心", font=("Arial", 16, "bold"), foreground="#4a90e2")
        decor_label.pack(pady=20)
        
        # 创建配置项
        config_frame = ttk.LabelFrame(self.config_frame, text="🔍 搜索配置", style="Decorative.TLabelframe")
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # 关键词配置
        keyword_label = ttk.Label(config_frame, text="💡 关键词：", font=("Arial", 11, "bold"))
        keyword_label.pack(padx=10, pady=5, anchor=tk.W)
        
        keyword_desc = ttk.Label(config_frame, text="多个关键词用逗号分隔，例如：pulsar, fast radio burst, neutron star", 
                               font=("Arial", 10, "italic"), foreground="#666666")
        keyword_desc.pack(padx=10, pady=2, anchor=tk.W)
        
        self.keyword_entry = ttk.Entry(config_frame, width=60, font=("Arial", 11))
        self.keyword_entry.insert(0, ", ".join(CONFIG["keywords"]))
        self.keyword_entry.pack(padx=10, pady=5, anchor=tk.W)
        
        # 领域配置
        field_label = ttk.Label(config_frame, text="🌌 领域：", font=("Arial", 11, "bold"))
        field_label.pack(padx=10, pady=15, anchor=tk.W)
        
        field_desc = ttk.Label(config_frame, text="多个领域用逗号分隔，例如：physics, astro-ph", 
                             font=("Arial", 10, "italic"), foreground="#666666")
        field_desc.pack(padx=10, pady=2, anchor=tk.W)
        
        self.field_entry = ttk.Entry(config_frame, width=60, font=("Arial", 11))
        self.field_entry.insert(0, ", ".join(CONFIG["fields"]))
        self.field_entry.pack(padx=10, pady=5, anchor=tk.W)
        
        # 保存按钮
        save_btn = ttk.Button(config_frame, text="💾 保存配置", command=self.save_config, style="TButton")
        save_btn.pack(padx=10, pady=20, anchor=tk.W)
        
        # 添加卡通提示
        tip_label = ttk.Label(self.config_frame, text="💡 提示：配置保存后会立即生效，无需重启程序！", 
                           font=("Arial", 11, "italic"), foreground="#ff6b6b")
        tip_label.pack(pady=20, padx=20, anchor=tk.W)
        
    def build_query(self, keywords: List[str]) -> str:
        """构建搜索查询字符串。"""
        return " OR ".join(f"\"{keyword}\"" for keyword in keywords)
        
    def build_categories(self, fields: List[str]) -> List[str]:
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
        
    async def search_papers(self) -> List[Dict[str, Any]]:
        """搜索特定领域和关键词的论文。"""
        logger.info("开始搜索论文...")
        
        # 构建查询和分类
        query = self.build_query(CONFIG["keywords"])
        categories = self.build_categories(CONFIG["fields"])
        
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
                    "pdf_url": result.pdf_url,
                }
                results.append(paper)
                
                # 限制结果数量
                if len(results) >= CONFIG["max_results"]:
                    break
        
        logger.info(f"搜索完成，找到 {len(results)} 篇论文")
        return results
        
    def check_new_papers(self):
        """检查新论文。"""
        self.status_label.config(text="正在检查新论文...")
        
        # 在新线程中执行搜索
        def search_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            papers = loop.run_until_complete(self.search_papers())
            self.current_papers = papers
            
            # 更新状态
            self.root.after(0, lambda: self.status_label.config(text=f"找到 {len(papers)} 篇新论文"))
        
        thread = threading.Thread(target=search_thread)
        thread.start()
        
    def play_latest_papers(self):
        """播放最新论文。"""
        if not self.current_papers:
            messagebox.showinfo("提示", "没有找到新论文，请先检查新论文")
            return
        
        self.is_playing = True
        self.current_paper_index = 0
        self.play_next_paper()
        
    def play_next_paper(self):
        """播放下一篇论文。"""
        if not self.is_playing or self.current_paper_index >= len(self.current_papers):
            self.is_playing = False
            self.status_label.config(text="播放完成")
            return
        
        paper = self.current_papers[self.current_paper_index]
        
        # 打开播放界面
        self.open_play_window(paper)
        
    def stop_playback(self):
        """停止播放。"""
        self.is_playing = False
        self.status_label.config(text="播放已停止")
        
    def play_paper_speech(self, paper):
        """播放论文语音。"""
        # 清理LaTeX数学标识符
        title = re.sub(r'\$.*?\$', '', paper["title"])
        abstract = re.sub(r'\$.*?\$', '', paper["abstract"])
        
        # 翻译标题和摘要
        translated_title = translator.translate(title)
        translated_abstract = translator.translate(abstract)
        
        # 构建总结
        summary = f"{translated_title}：{translated_abstract}"
        
        # 在新线程中生成并播放语音
        def speech_thread():
            try:
                import os
                import tempfile
                
                # 生成语音文件
                temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False, mode='wb')
                temp_file_path = temp_file.name
                temp_file.close()
                
                logger.info(f"生成语音文件: {temp_file_path}")
                
                # 使用edge-tts生成语音（同步方式）
                import subprocess
                import sys
                
                # 转义命令中的特殊字符
                escaped_summary = summary.replace('"', '\\"').replace("'", "\\'")
                escaped_temp_path = temp_file_path.replace('\\', '\\\\')
                
                # 构建edge-tts命令
                cmd = [
                    sys.executable, "-c",
                    f"import edge_tts; import asyncio; asyncio.run(edge_tts.Communicate('{escaped_summary}', 'zh-CN-XiaoxiaoNeural').save('{escaped_temp_path}'))"
                ]
                
                logger.info(f"执行命令: {' '.join(cmd)}")
                
                # 执行命令
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                
                # 检查文件是否存在
                if not os.path.exists(temp_file_path):
                    logger.error(f"生成的语音文件不存在: {temp_file_path}")
                    return
                
                logger.info(f"语音文件生成成功，大小: {os.path.getsize(temp_file_path)}字节")
                
                # 播放语音
                self.play_audio_file(temp_file_path)
                
                # 删除临时文件
                os.unlink(temp_file_path)
                logger.info(f"临时文件已删除: {temp_file_path}")
            except Exception as e:
                logger.error(f"播放语音失败: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=speech_thread)
        thread.start()
        
    def play_audio_file(self, file_path):
        """播放音频文件。"""
        try:
            import pygame
            
            # 初始化pygame
            pygame.mixer.init()
            
            # 加载并播放语音文件
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            
            # 等待播放完成
            while pygame.mixer.music.get_busy() and self.is_playing:
                time.sleep(0.1)
            
            # 清理资源
            pygame.mixer.quit()
        except Exception as e:
            logger.error(f"使用pygame播放语音失败: {e}")
            
            # 回退到系统播放器
            import subprocess
            if os.name == 'nt':
                subprocess.Popen(['start', '', file_path], shell=True)
            else:
                subprocess.Popen(['open', file_path])
        
    def favorite_paper(self, paper, window):
        """收藏论文。"""
        try:
            # 保存PDF文件
            import requests
            
            # 创建收藏目录
            favorite_dir = CONFIG["favorite_path"]
            os.makedirs(favorite_dir, exist_ok=True)
            
            # 下载PDF
            pdf_url = paper["pdf_url"]
            pdf_path = os.path.join(favorite_dir, f"{paper['id']}.pdf")
            
            response = requests.get(pdf_url)
            response.raise_for_status()
            
            with open(pdf_path, "wb") as f:
                f.write(response.content)
            
            # 保存论文信息
            self.favorites.append(paper)
            self.save_favorites()
            
            # 更新收藏列表
            self.update_favorite_list()
            
            messagebox.showinfo("成功", "论文已收藏")
        except Exception as e:
            logger.error(f"收藏论文失败: {e}")
            messagebox.showerror("错误", f"收藏失败: {str(e)}")
        
    def load_favorites(self):
        """加载收藏列表。"""
        try:
            favorite_file = os.path.join(CONFIG["favorite_path"], "favorites.json")
            if os.path.exists(favorite_file):
                with open(favorite_file, "r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
        except Exception as e:
            logger.error(f"加载收藏列表失败: {e}")
            self.favorites = []
        
    def save_favorites(self):
        """保存收藏列表。"""
        try:
            favorite_file = os.path.join(CONFIG["favorite_path"], "favorites.json")
            with open(favorite_file, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存收藏列表失败: {e}")
        
    def update_favorite_list(self):
        """更新收藏列表。"""
        # 清空现有列表
        for item in self.favorite_tree.get_children():
            self.favorite_tree.delete(item)
        
        # 添加收藏项
        for paper in self.favorites:
            # 获取第一作者
            first_author = paper["authors"][0] if paper["authors"] else ""
            
            # 提取年份
            try:
                published_date = datetime.fromisoformat(paper["published"])
                year = str(published_date.year)
            except:
                year = ""
            
            self.favorite_tree.insert("", tk.END, values=(paper["title"], first_author, year))
    
    def fill_about_frame(self):
        """填充关于页面内容，添加卡通元素和丰富的颜色。"""
        # 添加卡通装饰
        cartoon_label = ttk.Label(self.about_frame, text="🚀", font=("Arial", 48))
        cartoon_label.pack(pady=20)
        
        about_label = ttk.Label(self.about_frame, text="ArXiv论文新闻播报", font=("Arial", 16, "bold"), foreground="#4a90e2")
        about_label.pack(pady=10)
        
        version_label = ttk.Label(self.about_frame, text="📌 版本: 1.0.0", font=("Arial", 11, "italic"))
        version_label.pack(pady=5)
        
        author_label = ttk.Label(self.about_frame, text="👨‍💻 作者: ArXiv News Team", font=("Arial", 11, "italic"))
        author_label.pack(pady=5)
        
        desc_label = ttk.Label(self.about_frame, text="🌟 每天定时收集arXiv上的论文，并进行语音播报\n✨ 让科学探索变得更有趣！", 
                              wraplength=600, font=("Arial", 11), foreground="#333333")
        desc_label.pack(pady=10)
        
        # 添加卡通装饰
        fun_label = ttk.Label(self.about_frame, text="🎉 感谢使用！", font=("Arial", 12, "bold"), foreground="#ff6b6b")
        fun_label.pack(pady=20)
        
        # 添加技术栈信息
        tech_label = ttk.Label(self.about_frame, text="💡 技术栈: Python, Tkinter, ArXiv API, Edge-TTS", 
                              font=("Arial", 10, "italic"), foreground="#666666")
        tech_label.pack(pady=5)
        
    def add_to_auto_start(self):
        """将程序添加到Windows自动运行列表。"""
        if os.name != 'nt':
            return
        
        try:
            import winreg
            import sys
            
            # 获取当前程序路径
            exe_path = sys.executable
            script_path = os.path.abspath(__file__)
            command = f'"{exe_path}" "{script_path}"'
            
            # 打开注册表
            key_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                # 添加到自动运行
                winreg.SetValueEx(key, "ArXivNewsApp", 0, winreg.REG_SZ, command)
                logger.info("程序已添加到Windows自动运行列表")
        except Exception as e:
            logger.error(f"添加到Windows自动运行列表失败: {e}")
            messagebox.showerror("错误", f"添加到自动运行失败: {str(e)}")
        
    def view_favorite(self):
        """查看收藏详情，添加卡通元素和丰富的颜色。"""
        selected_item = self.favorite_tree.selection()
        if not selected_item:
            messagebox.showinfo("提示", "请选择一篇论文")
            return
        
        # 获取选中的论文
        index = self.favorite_tree.index(selected_item[0])
        paper = self.favorites[index]
        
        # 打开查看窗口
        view_window = tk.Toplevel(self.root)
        view_window.title("📚 论文详情")
        view_window.geometry("800x600")
        view_window.configure(bg="#f0f8ff")
        
        # 创建标题标签
        title_label = ttk.Label(view_window, text=paper["title"], font=("Arial", 14, "bold"), wraplength=750, foreground="#4a90e2")
        title_label.pack(pady=20, padx=20, anchor=tk.W)
        
        # 创建作者标签
        authors = ", ".join(paper["authors"])[:150] + "..." if len(", ".join(paper["authors"])) > 150 else ", ".join(paper["authors"])
        authors_label = ttk.Label(view_window, text=f"👤 作者: {authors}", font=("Arial", 11, "italic"))
        authors_label.pack(pady=5, padx=20, anchor=tk.W)
        
        # 添加发布日期
        try:
            published_date = datetime.fromisoformat(paper["published"])
            date_str = published_date.strftime("%Y-%m-%d")
            date_label = ttk.Label(view_window, text=f"📅 发布日期: {date_str}", font=("Arial", 11, "italic"))
            date_label.pack(pady=5, padx=20, anchor=tk.W)
        except:
            pass
        
        # 添加分类信息
        categories = ", ".join(paper["categories"])[:100] + "..." if len(", ".join(paper["categories"])) > 100 else ", ".join(paper["categories"])
        category_label = ttk.Label(view_window, text=f"🏷️ 分类: {categories}", font=("Arial", 11, "italic"))
        category_label.pack(pady=5, padx=20, anchor=tk.W)
        
        # 创建摘要滚动文本
        abstract_frame = ttk.LabelFrame(view_window, text="📝 摘要", style="Decorative.TLabelframe")
        abstract_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        abstract_text = scrolledtext.ScrolledText(abstract_frame, wrap=tk.WORD, font=("Arial", 11), bg="white", fg="#333333", relief=tk.FLAT, bd=0)
        abstract_text.insert(tk.END, paper["abstract"])
        abstract_text.config(state=tk.DISABLED)
        abstract_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建按钮框架
        btn_frame = ttk.Frame(view_window, style="Card.TFrame")
        btn_frame.pack(pady=20, padx=20, fill=tk.X)
        
        # 打开PDF按钮
        pdf_btn = ttk.Button(btn_frame, text="📄 打开PDF", command=lambda: self.open_pdf(paper))
        pdf_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 关闭按钮
        close_btn = ttk.Button(btn_frame, text="❌ 关闭", command=view_window.destroy)
        close_btn.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
    def open_pdf(self, paper):
        """打开PDF文件。"""
        pdf_path = os.path.join(CONFIG["favorite_path"], f"{paper['id']}.pdf")
        if os.path.exists(pdf_path):
            os.startfile(pdf_path)  # Windows
        else:
            messagebox.showinfo("提示", "PDF文件不存在")
        
    def delete_favorite(self):
        """删除收藏。"""
        selected_item = self.favorite_tree.selection()
        if not selected_item:
            messagebox.showinfo("提示", "请选择一篇论文")
            return
        
        # 获取选中的论文
        index = self.favorite_tree.index(selected_item[0])
        paper = self.favorites[index]
        
        # 确认删除
        if messagebox.askyesno("确认", "确定要删除这篇收藏吗？"):
            # 删除PDF文件
            pdf_path = os.path.join(CONFIG["favorite_path"], f"{paper['id']}.pdf")
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            
            # 从列表中删除
            del self.favorites[index]
            self.save_favorites()
            self.update_favorite_list()
        
    def save_config(self):
        """保存配置。"""
        # 获取配置值
        keywords = self.keyword_entry.get().split(",")
        keywords = [k.strip() for k in keywords if k.strip()]
        
        fields = self.field_entry.get().split(",")
        fields = [f.strip() for f in fields if f.strip()]
        
        # 更新配置
        CONFIG["keywords"] = keywords
        CONFIG["fields"] = fields
        
        # 保存配置到文件
        try:
            config_file = "arxiv_news_config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(CONFIG, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("成功", "配置已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
        
    def reminder_loop(self):
        """定时提醒循环。"""
        while True:
            # 检查是否启用提醒
            if not self.reminder_enabled.get():
                time.sleep(60)  # 每分钟检查一次
                continue
            
            # 检查是否跳过今天
            if self.skip_today:
                # 重置跳过状态
                now = datetime.now()
                if now.hour >= CONFIG["reminder_end_time"]:
                    self.skip_today = False
                time.sleep(60)  # 每分钟检查一次
                continue
            
            # 检查是否是周一至周五（0-4表示周一至周五）
            now = datetime.now()
            if now.weekday() >= 5:  # 5表示周六，6表示周日
                time.sleep(3600)  # 周末每小时检查一次
                continue
            
            # 检查当前时间是否在提醒时间段内
            if now.hour < CONFIG["reminder_start_time"] or now.hour >= CONFIG["reminder_end_time"]:
                time.sleep(60)  # 每分钟检查一次
                continue
            
            # 检查是否到了提醒时间（每两小时一次）
            if now.hour % 2 == 0:
                # 检查是否已经提醒过
                last_reminder_file = "last_reminder.txt"
                need_reminder = True
                
                if os.path.exists(last_reminder_file):
                    with open(last_reminder_file, "r") as f:
                        last_reminder = f.read().strip()
                    
                    # 检查是否今天已经提醒过
                    if last_reminder == now.strftime("%Y-%m-%d %H"):
                        need_reminder = False
                
                if need_reminder:
                    # 保存最后提醒时间
                    with open(last_reminder_file, "w") as f:
                        f.write(now.strftime("%Y-%m-%d %H"))
                    
                    # 检查新论文
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    papers = loop.run_until_complete(self.search_papers())
                    
                    if papers:
                        self.current_papers = papers
                        # 显示提醒窗口
                        self.root.after(0, self.show_reminder_window)
            
            time.sleep(60)  # 每分钟检查一次
            
    def run(self):
        """运行应用程序。"""
        self.root.mainloop()


if __name__ == "__main__":
    app = ArxivNewsApp()
    app.run()
