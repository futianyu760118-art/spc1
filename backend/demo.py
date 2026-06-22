
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )

if __name__ == "__main__":
    """测试密码生成"""
    password = "123456"
    hashed = get_password_hash(password)
    print(f"原始密码: {password}")
    print(f"哈希密码: {hashed}")

    # 验证密码
    is_valid = verify_password("123456", "$2b$12$O.JSPIVT3Fpz9.QcXoRhcOP/2SRtJ6YnMdwCMRkqC1p7bhWC4M1Xq")
    print(f"密码是否有效: {is_valid}")
