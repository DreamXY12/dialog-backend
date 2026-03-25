# 共用模型

from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from sql.start import Base

# 病人和护士共用的反馈数据库
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)

    rating = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)

    attachments = Column(Text, nullable=True)  # JSON字符串

    role = Column(String(20), nullable=False)
    phone = Column(String(20), nullable=False)

    ai_context = Column(Text, nullable=True)

    create_time = Column(DateTime, default=datetime.utcnow)
