import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Optional, Literal
import redis
import logging

# 从db_models.py导入Base
from src.data.db_models import Base, BaseModel

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 环境配置项
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_EXPIRATION = int(os.environ.get("REDIS_EXPIRATION", 3600 * 24 * 7))  # 默认7天
AUTO_INITIALIZE = os.environ.get("AUTO_INITIALIZE", "true").lower() == "true"
CACHE_MODE = os.environ.get("CACHE_MODE", "full").lower()  # 'full', 'sqlite', 'redis', 'memory', 'none'

# 引擎和会话工厂
_engine = None
_SessionLocal = None
_redis_client = None
_db_enabled = True
_redis_enabled = True

def is_db_enabled() -> bool:
    """检查数据库是否启用"""
    return _db_enabled and _engine is not None

def is_redis_enabled() -> bool:
    """检查Redis是否启用"""
    return _redis_enabled and _redis_client is not None

def get_cache_mode() -> str:
    """获取当前缓存模式
    
    缓存模式优先级：
    1. 'full' - 同时使用 SQLite 和 Redis (默认)
    2. 'sqlite' - 仅使用 SQLite 作为持久存储
    3. 'redis' - 仅使用 Redis 作为缓存
    4. 'memory' - 仅使用内存缓存
    5. 'none' - 禁用缓存
    
    返回值:
        str: 缓存模式 ('full', 'sqlite', 'redis', 'memory', 'none')
    """
    # 根据配置和可用性确定实际模式
    if CACHE_MODE == 'full' and is_db_enabled() and is_redis_enabled():
        return 'full'
    elif (CACHE_MODE == 'full' or CACHE_MODE == 'sqlite') and is_db_enabled():
        return 'sqlite'
    elif (CACHE_MODE == 'full' or CACHE_MODE == 'redis') and is_redis_enabled():
        return 'redis'
    elif CACHE_MODE == 'none':
        return 'none'
    else:
        return 'memory'  # 默认回退到内存缓存

def set_cache_mode(mode: Literal['full', 'sqlite', 'redis', 'memory', 'none']):
    """设置缓存模式
    
    Args:
        mode: 缓存模式
            - 'full': 同时使用SQLite和Redis (默认)
            - 'sqlite': 仅使用SQLite作为持久存储
            - 'redis': 仅使用Redis作为缓存
            - 'memory': 仅使用内存缓存
            - 'none': 禁用缓存
    """
    global CACHE_MODE
    if mode in ['full', 'sqlite', 'redis', 'memory', 'none']:
        CACHE_MODE = mode
        logger.info(f"缓存模式已设置为：{mode}")
        
        # 如果设置了 sqlite 模式但数据库未初始化，则尝试初始化
        if mode in ['full', 'sqlite'] and not is_db_enabled():
            init_db()
    else:
        logger.warning(f"无效的缓存模式：{mode}，使用默认值 'full'")
        CACHE_MODE = 'full'

def init_db() -> None:
    """初始化数据库连接
    
    这个函数会连接到数据库（如果可能）并创建所有表（如果它们不存在）
    """
    global _engine, _SessionLocal, _db_enabled
    
    if _engine:
        return  # 数据库已初始化
    
    try:
        # 尝试创建引擎和会话工厂
        logger.info("初始化数据库连接...")
        _engine = create_engine(DATABASE_URL)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        
        # 创建所有表
        Base.metadata.create_all(bind=_engine)
        
        # 测试连接 - 修复文本SQL表达式问题
        with _SessionLocal() as session:
            session.execute(text("SELECT 1"))
        
        _db_enabled = True
        logger.info("数据库连接成功!")
        
    except Exception as e:
        logger.warning(f"数据库初始化失败: {e}")
        _db_enabled = False
        
        if CACHE_MODE in ['full', 'sqlite']:
            logger.info("回退到Redis缓存模式")
            if CACHE_MODE == 'sqlite':
                set_cache_mode('redis') # 自动切换到Redis模式
    
    # 初始化Redis连接
    init_redis()

def init_redis() -> None:
    """初始化Redis连接"""
    global _redis_client, _redis_enabled
    
    if _redis_client:
        return  # Redis已初始化
        
    if CACHE_MODE == 'none':
        logger.info("缓存已禁用")
        _redis_enabled = False
        return
        
    try:
        logger.info("初始化Redis连接...")
        _redis_client = redis.from_url(REDIS_URL)
        _redis_client.ping()  # 测试连接
        _redis_enabled = True
        logger.info("Redis连接成功!")
    except Exception as e:
        logger.warning(f"Redis初始化失败: {e}")
        _redis_enabled = False
        
        if CACHE_MODE in ['full', 'redis']:
            logger.info("回退到SQLite或内存缓存模式")
            if CACHE_MODE == 'redis':
                set_cache_mode('sqlite' if is_db_enabled() else 'memory') # 自动切换到SQLite或内存模式

def get_db() -> Generator[Session, None, None]:
    """获取数据库会话
    
    如果数据库未启用，则会引发StopIteration异常
    
    Yields:
        Generator[Session, None, None]: 数据库会话
    """
    if not _db_enabled or not _engine:
        yield None
        return
        
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_redis() -> Optional[redis.Redis]:
    """获取Redis客户端
    
    Returns:
        Optional[redis.Redis]: Redis客户端，如果未启用则为None
    """
    return _redis_client if _redis_enabled else None

def generate_cache_key(data_type: str, **kwargs) -> str:
    """生成缓存键
    
    Args:
        data_type: 数据类型（如'prices', 'metrics'）
        **kwargs: 其他参数
    
    Returns:
        str: 缓存键
    """
    key_parts = [data_type]
    
    for k, v in sorted(kwargs.items()):
        if v is not None:
            key_parts.append(f"{k}:{v}")
    
    return ":".join(key_parts)

# 如果AUTO_INITIALIZE为true，则自动初始化
if AUTO_INITIALIZE:
    init_db()

# 用于模型转换的工具函数
def model_to_dict(model) -> dict:
    """将SQLAlchemy模型对象转换为字典"""
    if hasattr(model, '__table__'):
        return {column.name: getattr(model, column.name) 
                for column in model.__table__.columns}
    return {}

def dict_to_model(model_class, data: dict):
    """将字典转换为SQLAlchemy模型对象"""
    return model_class(**data) 