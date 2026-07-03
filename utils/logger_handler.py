from src.utils.logger_handler import get_abs_path
import os
import logging
from datetime import datetime

# 日志保存根目录
LOG_ROOT = get_abs_path("logs")

# 确保日志目录存在
os.makedirs(LOG_ROOT, exist_ok=True)

# 日志的格式配置
DEFAULT_LOG_FORMATTER = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)


def get_logger(
        name:str = 'agent',
        console_level:int = logging.DEBUG,
        file_level:int = logging.DEBUG,
        log_file = None
) -> logging.Logger:
    #创建日志管理器
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 控制台控制Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMATTER)
    logger.addHandler(console_handler)

    # 文件日志handler
    if not log_file:
        # 日志文件的存放路径
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(DEFAULT_LOG_FORMATTER)

        logger.addHandler(file_handler)

    return logger

# 快捷获取日志管理器
logger = get_logger()
