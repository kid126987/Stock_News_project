import os
import sys
import unittest
from unittest.mock import patch

# 確保載入專案的 db 模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestDBConfig(unittest.TestCase):
    @patch.dict(os.environ, {"DB_TYPE": "sqlite"})
    def test_sqlite_config(self):
        from db.setup import is_supabase_configured
        self.assertFalse(is_supabase_configured())

    @patch.dict(os.environ, {"DB_TYPE": "postgres"})
    def test_postgres_config(self):
        from db.setup import is_supabase_configured
        self.assertFalse(is_supabase_configured())
        
    @patch.dict(os.environ, {"DB_TYPE": "supabase", "SUPABASE_DB_URL": "postgresql://postgres:pwd@db.abc.supabase.co:5432/postgres"})
    def test_supabase_configured_with_url(self):
        from db.setup import is_supabase_configured, get_supabase_db_url
        self.assertTrue(is_supabase_configured())
        self.assertEqual(get_supabase_db_url(), "postgresql://postgres:pwd@db.abc.supabase.co:5432/postgres")

    @patch.dict(os.environ, {"DB_TYPE": "supabase", "DB_HOST": "db.abc.supabase.co", "DB_PASSWORD": "pwd", "DB_USER": "postgres", "DB_PORT": "5432", "DB_NAME": "postgres"})
    def test_supabase_configured_without_url(self):
        from db.setup import is_supabase_configured, get_supabase_db_url
        self.assertTrue(is_supabase_configured())
        self.assertEqual(get_supabase_db_url(), "postgresql://postgres:pwd@db.abc.supabase.co:5432/postgres?sslmode=require")

    @patch.dict(os.environ, {"SUPABASE_DB_URL": "postgresql://postgres:pwd@db.abc.supabase.co:5432/postgres?sslmode=require"})
    def test_supabase_configured_only_url(self):
        from db.setup import is_supabase_configured, get_supabase_db_url
        self.assertTrue(is_supabase_configured())
        self.assertEqual(get_supabase_db_url(), "postgresql://postgres:pwd@db.abc.supabase.co:5432/postgres?sslmode=require")

if __name__ == "__main__":
    unittest.main()
