from core.risk_engine import RiskEngine
import pytest

import asyncio
import pytest_asyncio
from sql.crud import get_case_by_id
from fastapi import Depends
from typing import Annotated
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sql.start import engine


# @pytest.mark.asyncio
# async def test_risk_engine(get_db: AsyncSession):
#     db = get_db
#     test_case = await get_case_by_id(db, case_id=4)
#     re = RiskEngine(time_spec=2, case=test_case)
#     result = re()
#     print(f"the result for case {2} is: " + result)
#     assert True 


# @pytest_asyncio.fixture(scope='function')
# async def get_db():
 
#     async_session = sessionmaker(
#         engine, 
#         class_=AsyncSession, 
#         expire_on_commit=False
#     )
#     async with async_session() as session:
#         yield session


# @pytest.fixture(scope='session')
# def event_loop():
#     """
#     Creates an instance of the default event loop for the test session.
#     """
#     policy = asyncio.get_event_loop_policy()
#     loop = policy.new_event_loop()
#     yield loop
#     loop.close()