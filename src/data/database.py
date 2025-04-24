import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Optional
import redis
import logging

from data.db_models import Base

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 环境配置项
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_EXPIRATION = int(os.environ.get("REDIS_EXPIRATION", 3600 * 24 * 7))  # 默认7天
AUTO_INITIALIZE = os.environ.get("AUTO_INITIALIZE", "true").lower() == "true"
CACHE_MODE = os.environ.get("CACHE_MODE", "full").lower()  # 'full', 'redis', 'memory', 'none'

# 创建SQLAlchemy基类
Base = declarative_base()

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
    
    返回值:
        str: 缓存模式 ('full', 'redis', 'memory', 'none')
    """
    # 根据配置和可用性确定实际模式
    if CACHE_MODE == 'full' and is_db_enabled() and is_redis_enabled():
        return 'full'
    elif (CACHE_MODE == 'full' or CACHE_MODE == 'redis') and is_redis_enabled():
        return 'redis'
    elif CACHE_MODE == 'none':
        return 'none'
    else:
        return 'memory'  # 默认回退到内存缓存

class BaseModel:
    """所有模型的基类"""
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        from data.db_models import Base
        Base.metadata.create_all(bind=_engine)
        
        # 测试连接
        with _SessionLocal() as session:
            session.execute("SELECT 1")
        
        _db_enabled = True
        logger.info("数据库连接成功!")
        
    except Exception as e:
        logger.warning(f"数据库初始化失败: {e}")
        _db_enabled = False
        
        if CACHE_MODE in ['full', 'redis']:
            logger.info("回退到Redis缓存模式")
        else:
            logger.info("回退到内存缓存模式")
    
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
            logger.info("回退到内存缓存模式")

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