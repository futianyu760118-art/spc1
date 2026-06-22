#!/usr/bin/env python3
"""Check existing users in the database"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, select
from app.core.database import AsyncSessionLocal
from app.models.basicdata.user import SysUser


async def check_users():
    """Check existing users in the database"""
    print("Checking existing users in the database...\n")
    
    async with AsyncSessionLocal() as session:
        # Query all users
        result = await session.execute(select(SysUser))
        users = result.scalars().all()
        
        if not users:
            print("No users found in the database!")
            print("You need to run the database initialization script.")
            return
        
        print(f"Found {len(users)} user(s):\n")
        print(f"{'ID':<4} {'Username':<20} {'Display Name':<20} {'Role ID':<8}")
        print("-" * 60)
        
        for user in users:
            print(f"{user.id:<4} {user.username:<20} {user.display_name:<20} {user.role_id or 'N/A':<8}")
        
        print("\n" + "="*60)
        print("\nDefault password for initialized users is: admin123")
        print("\nIf you don't see the admin user, you may need to run the init script.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_users())
