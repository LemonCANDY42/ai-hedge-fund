import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

# 添加父目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 关闭自动初始化
os.environ["AUTO_INITIALIZE"] = "false"

from data.database import init_db, is_db_enabled, is_redis_enabled, get_cache_mode
from data.cache import get_cache, init_cache, PersistentCache

class TestCacheSystem(unittest.TestCase):
    """测试缓存系统的各种模式"""
    
    def setUp(self):
        """每个测试前的设置"""
        # 清除环境变量以确保干净的测试环境
        if "CACHE_MODE" in os.environ:
            del os.environ["CACHE_MODE"]
        
        # 模拟数据
        self.test_data = [
            {
                "ticker": "AAPL",
                "time": "2023-01-01T00:00:00",
                "open": 100.0,
                "close": 105.0,
                "high": 107.0,
                "low": 99.0,
                "volume": 1000000
            },
            {
                "ticker": "AAPL",
                "time": "2023-01-02T00:00:00",
                "open": 105.0,
                "close": 110.0,
                "high": 112.0,
                "low": 104.0,
                "volume": 1200000
            }
        ]

    @patch('data.database._engine', None)
    @patch('data.database._db_enabled', False)
    @patch('data.database._redis_client', None)
    @patch('data.database._redis_enabled', False)
    def test_memory_cache_mode(self):
        """测试内存缓存模式"""
        os.environ["CACHE_MODE"] = "memory"
        
        # 初始化缓存系统
        cache = init_cache()
        
        # 验证缓存模式
        self.assertEqual(get_cache_mode(), "memory")
        self.assertFalse(is_db_enabled())
        self.assertFalse(is_redis_enabled())
        
        # 保存数据
        result = cache.set_prices("AAPL", self.test_data)
        self.assertTrue(result)
        
        # 读取数据
        cached_data = cache.get_prices("AAPL")
        self.assertEqual(len(cached_data), 2)
        self.assertEqual(cached_data[0]["ticker"], "AAPL")
        self.assertEqual(cached_data[0]["close"], 105.0)

    @patch('data.database._engine', MagicMock())
    @patch('data.database._db_enabled', True)
    @patch('data.database._redis_client', MagicMock())
    @patch('data.database._redis_enabled', True)
    @patch('data.database._SessionLocal')
    @patch('data.cache.PersistentCache._redis_get')
    @patch('data.cache.PersistentCache._redis_set')
    def test_full_cache_mode(self, mock_redis_set, mock_redis_get, mock_session):
        """测试完整缓存模式 (Redis + DB)"""
        os.environ["CACHE_MODE"] = "full"
        
        # 模拟数据库会话
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        
        # 初始化缓存系统
        cache = init_cache()
        
        # 验证缓存模式
        self.assertEqual(get_cache_mode(), "full")
        self.assertTrue(is_db_enabled())
        self.assertTrue(is_redis_enabled())
        
        # 模拟Redis未命中
        mock_redis_get.return_value = None
        
        # 模拟数据库查询
        mock_price = MagicMock()
        mock_price.ticker = "AAPL"
        mock_price.time = "2023-01-01T00:00:00"
        mock_price.open = 100.0
        mock_price.close = 105.0
        mock_price.high = 107.0
        mock_price.low = 99.0
        mock_price.volume = 1000000
        
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = [mock_price]
        mock_db.query.return_value = mock_query
        
        # 读取数据
        result = cache.get_prices("AAPL")
        
        # 验证Redis查询
        mock_redis_get.assert_called_once()
        
        # 验证数据库查询
        mock_db.query.assert_called_once()
        
        # 验证Redis缓存更新
        mock_redis_set.assert_called_once()
        
        # 验证返回结果
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "AAPL")
        self.assertEqual(result[0]["close"], 105.0)

    @patch('data.database._engine', None)
    @patch('data.database._db_enabled', False)
    @patch('data.database._redis_client', MagicMock())
    @patch('data.database._redis_enabled', True)
    @patch('data.cache.PersistentCache._redis_get')
    @patch('data.cache.PersistentCache._redis_set')
    def test_redis_cache_mode(self, mock_redis_set, mock_redis_get):
        """测试仅Redis缓存模式"""
        os.environ["CACHE_MODE"] = "redis"
        
        # 初始化缓存系统
        cache = init_cache()
        
        # 验证缓存模式
        self.assertEqual(get_cache_mode(), "redis")
        self.assertFalse(is_db_enabled())
        self.assertTrue(is_redis_enabled())
        
        # 模拟Redis命中
        mock_redis_get.return_value = self.test_data
        
        # 读取数据
        result = cache.get_prices("AAPL")
        
        # 验证Redis查询
        mock_redis_get.assert_called_once()
        
        # 验证返回结果
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["ticker"], "AAPL")
        self.assertEqual(result[0]["close"], 105.0)
        
        # 模拟Redis未命中然后设置数据
        mock_redis_get.reset_mock()
        mock_redis_get.return_value = None
        
        # 保存数据
        result = cache.set_prices("AAPL", self.test_data)
        self.assertTrue(result)
        
        # 验证Redis更新
        mock_redis_set.assert_called()

    @patch('data.database._engine', None)
    @patch('data.database._db_enabled', False)
    @patch('data.database._redis_client', None)
    @patch('data.database._redis_enabled', False)
    def test_no_cache_mode(self):
        """测试无缓存模式"""
        os.environ["CACHE_MODE"] = "none"
        
        # 初始化缓存系统
        cache = init_cache()
        
        # 验证缓存模式
        self.assertEqual(get_cache_mode(), "none")
        self.assertFalse(is_db_enabled())
        self.assertFalse(is_redis_enabled())
        
        # 尝试读取数据（应返回空列表）
        result = cache.get_prices("AAPL")
        self.assertEqual(result, [])
        
        # 尝试保存数据（应返回成功，但实际上未保存任何地方）
        result = cache.set_prices("AAPL", self.test_data)
        self.assertTrue(result)
        
        # 再次尝试读取数据（依然应返回空列表）
        result = cache.get_prices("AAPL")
        self.assertEqual(result, [])

if __name__ == "__main__":
    unittest.main() 