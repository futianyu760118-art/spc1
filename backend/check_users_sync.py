#!/usr/bin/env python3
"""Check existing users in the database using sync connection"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, create_engine, select
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.basicdata.user import SysUser


def check_users():
    """Check existing users in the database"""
    print("Checking existing users in the database...\n")
    
    settings = get_settings()
    
    # Create sync engine with longer timeout
    engine = create_engine(
        settings.DATABASE_URL_SYNC,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 30}
    )
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    try:
        with SessionLocal() as session:
            # Query all users
            result = session.execute(select(SysUser))
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
            
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("\nConnection info:")
        print(f"  Host: 183.134.254.14")
        print(f"  Port: 15432")
        print(f"  Username: root")
        print(f"  Database: spc_db")


if __name__ == "__main__":
    check_users()
