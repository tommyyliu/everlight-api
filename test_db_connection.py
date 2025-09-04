#!/usr/bin/env python3
"""
Test script to verify database connection to Supabase using SQLAlchemy
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

def test_db_connection():
    # Database connection details
    user = "postgres.vhcxvviechtocjfipcuw"
    # You'll need to replace [YOUR-PASSWORD] with the actual password
    password = "j/z47zRLCWD6Tkw"  # Replace this with actual password
    host = "aws-0-us-west-1.pooler.supabase.com"
    port = 6543
    dbname = "postgres"
    
    # Construct the database URL
    database_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
    
    print(f"Testing connection to: {host}:{port}/{dbname}")
    print(f"User: {user}")
    
    try:
        # Create engine
        engine = create_engine(database_url, echo=True)
        
        # Test connection
        with engine.connect() as connection:
            # Simple query to test connection
            result = connection.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"\n✅ Connection successful!")
            print(f"PostgreSQL version: {version}")
            
            # Test if we can see existing tables
            result = connection.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            
            tables = [row[0] for row in result.fetchall()]
            print(f"\nExisting tables: {tables}")
            
            return True
            
    except OperationalError as e:
        print(f"\n❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    # You can also read from environment variables if preferred
    if os.getenv("DATABASE_URL"):
        print("Using DATABASE_URL from environment")
        database_url = os.getenv("DATABASE_URL")
        try:
            engine = create_engine(database_url, echo=True)
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                print("✅ Environment DATABASE_URL works!")
        except Exception as e:
            print(f"❌ Environment DATABASE_URL failed: {e}")
    
    # Test with the provided credentials
    success = test_db_connection()
    
    if success:
        print("\n🎉 Database connection is working! You can proceed with Alembic migrations.")
    else:
        print("\n⚠️  Please check your credentials and try again.")