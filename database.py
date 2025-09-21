# database.py
import psycopg2
import logging
import time
from config import DATABASE_URL, MAX_HISTORY_LENGTH

logger = logging.getLogger(__name__)

class ChatHistoryDB:
    def __init__(self):
        self.db_url = DATABASE_URL
        self.conn = None
        self._connect()

    def _connect(self):
        if not self.db_url:
            raise ValueError("DATABASE_URL не установлена!")
        db_url = self.db_url.replace("postgres://", "postgresql://", 1) if self.db_url.startswith("postgres://") else self.db_url
        for attempt in range(5):
            try:
                self.conn = psycopg2.connect(db_url, sslmode='require')
                logger.info("Успешное подключение к PostgreSQL.")
                self._create_table()
                return
            except psycopg2.OperationalError as e:
                logger.error(f"Ошибка подключения к PostgreSQL (попытка {attempt + 1}): {e}")
                time.sleep(5)
        raise ConnectionError("Не удалось подключиться к PostgreSQL после нескольких попыток")

    def _create_table(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.conn.commit()

    def get_history(self, chat_id):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM (
                    SELECT role, content, timestamp FROM chat_history
                    WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s
                ) AS last_messages ORDER BY timestamp ASC;
            """, (chat_id, MAX_HISTORY_LENGTH))
            return [{"role": r, "content": c} for r, c in cur.fetchall()]

    def add_message(self, chat_id, role, content):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (chat_id, role, content) VALUES (%s, %s, %s)",
                (chat_id, role, content)
            )
            self.conn.commit()

    def reset_history(self, chat_id):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chat_history WHERE chat_id = %s", (chat_id,))
            self.conn.commit()

    def update_system_prompt(self, chat_id, new_prompt):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chat_history WHERE chat_id = %s AND role = 'system'", (chat_id,))
            self.add_message(chat_id, 'system', new_prompt)
            self.conn.commit()
