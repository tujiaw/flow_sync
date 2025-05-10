#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import requests
import logging
from pathlib import Path
import threading
from datetime import datetime
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('flow_sync.log')
    ]
)
logger = logging.getLogger(__name__)

# 文件路径
# 获取项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, 'src', 'config.json')
INPUT_DIR = os.path.join(ROOT_DIR, 'flow', 'input')
OUTPUT_DIR = os.path.join(ROOT_DIR, 'flow', 'output')

# 确保目录存在
Path(INPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


class FlowSync:
    def __init__(self):
        self.config = self._load_config()
        self.token = self.config.get('token', '')
        self.pull_interval = self.config.get('pull_interval', 10)  # 默认10秒
        self.bot_list = self.config.get('bot_list', [])
        self.base_url = 'https://next-app.1datatech.net/next/bot'
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        self.running = True

    def _load_config(self):
        """加载配置文件"""
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}

    def _calculate_md5(self, file_path):
        """计算文件MD5值"""
        try:
            with open(file_path, 'rb') as f:
                md5 = hashlib.md5(f.read()).hexdigest()
            return md5
        except Exception as e:
            logger.error(f"计算MD5失败: {e}")
            return None

    def _save_flow(self, bot_id, flow_data, last_modified: str | None = None):
        """保存flow数据到本地文件"""
        try:
            bot_name = next((bot['name'] for bot in self.bot_list if bot['id'] == bot_id), bot_id)
            file_path = os.path.join(INPUT_DIR, f"{bot_name}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(flow_data, f, ensure_ascii=False, indent=2)
            # 设置文件的修改时间为last_modified
            if last_modified:
                # 将字符串时间转换为时间戳
                time_struct = time.strptime(last_modified, '%Y-%m-%d %H:%M:%S')
                file_time = time.mktime(time_struct)
                os.utime(file_path, (file_time, file_time))
            logger.info(f"保存flow成功: {bot_name}")
            return True
        except Exception as e:
            logger.error(f"保存flow失败: {e}")
            return False

    def pull_flow(self, bot_id):
        """从服务器拉取flow配置"""
        try:
            url = f"{self.base_url}/{bot_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            response_json = response.json()
            if not response_json:
                logger.warning(f"拉取flow为空: {bot_id}")
                return None
                
            response_data = response_json['data']
            flow_data = response_data['flow_settings']
            bot_name = response_data['name']
            last_modified = response_data['gmt_modified']
            file_path = os.path.join(INPUT_DIR, f"{bot_name}.json")
            
            # 检查文件是否存在，如果不存在直接保存
            if not os.path.exists(file_path):
                self._save_flow(bot_id, flow_data, last_modified)
                return flow_data
                
            # 比较服务器和本地的修改时间
            local_modified = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            if last_modified > local_modified:
                # 服务器版本更新，保存到本地
                self._save_flow(bot_id, flow_data, last_modified)
                logger.info(f"根据时间戳更新flow成功: {bot_name} (服务器: {last_modified}, 本地: {local_modified})")
            else:
                logger.info(f"flow无需更新: {bot_name} (服务器: {last_modified}, 本地: {local_modified})")
                
            return flow_data
        except Exception as e:
            logger.error(f"拉取flow失败: {e}")
            return None

    def push_flow(self, bot_name, output_file_path):
        """将本地flow推送到服务器"""
        try:
            # 找到对应的bot_id
            bot_id = None
            for bot in self.bot_list:
                if bot['name'] == bot_name:
                    bot_id = bot['id']
                    break
            
            if not bot_id:
                logger.error(f"找不到bot_id: {bot_name}")
                return False
            
            with open(output_file_path, 'r', encoding='utf-8') as f:
                output_data = json.load(f)
            
            # 本地有变化一定更新，不再比对时间
            logger.info(f"准备更新flow: {bot_name}")
            
            # 发送POST请求
            url = f"{self.base_url}/{bot_id}/setting"
            response = requests.post(url, headers=self.headers, json=output_data)
            response.raise_for_status()
            
            logger.info(f"推送flow成功: {bot_name}")
            return True
        except Exception as e:
            logger.error(f"推送flow失败: {e}")
            return False

    def start_pull_schedule(self):
        """定时拉取所有bot的flow"""
        logger.info(f"开始定时拉取任务，间隔: {self.pull_interval}秒")
        while self.running:
            try:
                for bot in self.bot_list:
                    self.pull_flow(bot['id'])
                time.sleep(self.pull_interval)
            except Exception as e:
                logger.error(f"拉取任务异常: {e}")
                time.sleep(5)  # 出错后等待5秒再继续

    def stop(self):
        """停止所有任务"""
        self.running = False


class FileWatcher:
    def __init__(self, flow_sync, directory, interval=1):
        self.flow_sync = flow_sync
        self.directory = directory
        self.interval = interval
        self.last_modified_times = {}
        self.running = True

    def _get_file_list(self):
        """获取目录中的所有JSON文件"""
        return [f for f in os.listdir(self.directory) if f.endswith('.json')]

    def _check_for_changes(self):
        """检查文件是否有变化"""
        files = self._get_file_list()
        for file_name in files:
            file_path = os.path.join(self.directory, file_name)
            try:
                # 获取文件修改时间
                mtime = os.path.getmtime(file_path)
                
                # 如果文件是新的或者被修改了
                if file_path not in self.last_modified_times or mtime > self.last_modified_times[file_path]:
                    # 更新最后修改时间
                    self.last_modified_times[file_path] = mtime
                    
                    # 处理文件变化
                    bot_name = os.path.splitext(file_name)[0]
                    logger.info(f"检测到文件变化: {file_name}")
                    self.flow_sync.push_flow(bot_name, file_path)
            except Exception as e:
                logger.error(f"检查文件变化异常: {e}")

    def start(self):
        """开始监视文件变化"""
        logger.info(f"开始监视目录: {self.directory}")
        while self.running:
            try:
                self._check_for_changes()
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"文件监视异常: {e}")
                time.sleep(5)

    def stop(self):
        """停止监视"""
        self.running = False


def main():
    flow_sync = None
    watcher_thread = None
    pull_thread = None
    
    try:
        # 初始化
        flow_sync = FlowSync()
        
        if not flow_sync.bot_list:
            logger.error("配置文件中没有bot列表，请检查配置")
            return
        
        # 创建文件监视器
        file_watcher = FileWatcher(flow_sync, OUTPUT_DIR)
        
        # 创建并启动线程
        watcher_thread = threading.Thread(target=file_watcher.start)
        watcher_thread.daemon = True  # 设置为守护线程，主线程结束时自动结束
        watcher_thread.start()
        
        # 创建并启动定时拉取线程
        pull_thread = threading.Thread(target=flow_sync.start_pull_schedule)
        pull_thread.daemon = True
        pull_thread.start()
        
        # 主线程等待
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("程序已停止")
    except Exception as e:
        logger.error(f"程序异常: {e}")
    finally:
        # 清理资源
        if flow_sync:
            flow_sync.stop()


if __name__ == "__main__":
    main() 