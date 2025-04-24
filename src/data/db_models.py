from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from data.database import BaseModel

# 创建SQLAlchemy基类
Base = declarative_base()

class Price(Base, BaseModel):
    """
    Price data for a specific ticker at a specific time
    """
    __tablename__ = "prices"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), index=True, nullable=False)
    time = Column(String(32), index=True, nullable=False)  # ISO 8601格式
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint for ticker + time
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class FinancialMetric(Base, BaseModel):
    """
    Financial metrics for a specific ticker at a specific report period
    """
    __tablename__ = "financial_metrics"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), index=True, nullable=False)
    report_period = Column(String(32), index=True, nullable=False)  # ISO 8601格式的日期
    period = Column(String(16), index=True, nullable=False)  # 'annual', 'quarterly', 'ttm', etc.
    currency = Column(String(10))
    market_cap = Column(Float)
    enterprise_value = Column(Float)
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    ps_ratio = Column(Float)
    ev_to_ebitda = Column(Float)
    roe = Column(Float)
    roa = Column(Float)
    gross_margin = Column(Float)
    operating_margin = Column(Float)
    net_margin = Column(Float)
    revenue_growth = Column(Float)
    earnings_growth = Column(Float)
    dividend_yield = Column(Float)
    payout_ratio = Column(Float)
    current_ratio = Column(Float)
    quick_ratio = Column(Float)
    debt_to_equity = Column(Float)
    interest_coverage = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint for ticker + report_period + period
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class LineItem(Base, BaseModel):
    """
    Line items for financial statements
    """
    __tablename__ = "line_items"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), index=True, nullable=False)
    report_period = Column(String(32), index=True, nullable=False)  # ISO 8601格式的日期
    period_type = Column(String(16), index=True, nullable=False)  # 'annual', 'quarterly', etc.
    statement_type = Column(String(32), index=True, nullable=False)  # 'income', 'balance', 'cash_flow'
    
    # 财务数据项
    label = Column(String(128), nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint for ticker + report_period + period
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class InsiderTrade(Base, BaseModel):
    """
    Insider trades for a company
    """
    __tablename__ = "insider_trades"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), index=True, nullable=False)
    filing_date = Column(String(32), index=True, nullable=False)  # ISO 8601格式
    
    # 交易详情
    insider_name = Column(String(128))
    position = Column(String(128))
    transaction_type = Column(String(32))
    transaction_date = Column(String(32))
    shares = Column(Integer)
    price_per_share = Column(Float)
    total_value = Column(Float)
    shares_owned_after = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint based on filing_date, name, transaction_date
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class News(Base, BaseModel):
    """
    News articles for a company
    """
    __tablename__ = "company_news"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), index=True, nullable=False)
    date = Column(String(32), index=True, nullable=False)  # ISO 8601格式
    
    # 新闻详情
    title = Column(String(256))
    summary = Column(Text)
    source = Column(String(128))
    url = Column(String(512))
    sentiment = Column(Float, nullable=True)  # 情感分数，范围通常为 -1.0 到 1.0
    
    # 元数据和附加信息
    categories = Column(JSON, nullable=True)  # 主题分类，如 "盈利报告"、"管理变更" 等
    entities = Column(JSON, nullable=True)  # 提到的实体，如人员、公司等
    
    # Unique constraint based on url or combination of ticker, date, and title
    __table_args__ = (
        {'sqlite_autoincrement': True},
    ) 