# Flow Sync

这是一个自动同步Bot流程配置的工具，用于在本地和服务器之间同步flow.json文件。

## 功能

1. 定时从服务器拉取Bot的flow.json配置，保存到本地flow/input目录
2. 监视flow/output目录中的变化，自动将更新后的flow.json同步到服务器
3. 基于文件MD5和gmt_modified时间戳进行比较，避免不必要的同步

## 安装与使用

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配置config.json

```json
{
    "token": "你的API令牌",
    "pull_interval": 10,
    "bot_list": [
        {
            "id": "你的bot_id",
            "name": "bot名称"
        }
    ]
}
```

3. 运行程序

```bash
python src/flow_sync.py
```

## 目录结构

- flow/input: 存放从服务器拉取的flow.json文件
- flow/output: 存放本地修改后的flow.json文件（需要同步到服务器）
- src/flow_sync.py: 主程序
- src/config.json: 配置文件

## 工作流程

1. 程序启动后会定期从服务器拉取配置，并保存到flow/input目录
2. 当检测到flow/output目录中的文件发生变化时，程序会比较修改时间（gmt_modified字段）
3. 如果output目录中的文件比input目录中的更新，程序会自动将其同步到服务器