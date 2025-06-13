"""
Session Manager for StandardGPT
Håndterer samtalehistorikk og brukersesjoner
"""

import sqlite3
import uuid
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import os

@dataclass
class Conversation:
    """Samtale objekt"""
    id: str
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int = 0

@dataclass
class Message:
    """Melding i samtale"""
    id: int
    conversation_id: str
    question: str
    answer: str
    timestamp: datetime

class SessionManager:
    """Håndterer brukersesjoner og samtalehistorikk"""
    
    def __init__(self, db_path: str = "conversations.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialiser database tabeller"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            
            # Index for bedre performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_last_message 
                ON conversations(last_message_at DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation 
                ON messages(conversation_id, timestamp DESC)
            """)
    
    def generate_conversation_title(self, question: str, answer: str) -> str:
        """Generer samtale tittel basert på standarder nevnt"""
        # Søk etter standardnumre i spørsmål og svar
        standard_pattern = r'\b([A-Z]{1,10}[\s\-]?[0-9A-Z\-]{1,15}(?:[\:\+][0-9A-Z\-]{1,20})?)\b'
        
        standards_found = set()
        for text in [question, answer]:
            matches = re.findall(standard_pattern, text.upper())
            standards_found.update(matches[:3])  # Maks 3 standarder i tittel
        
        if standards_found:
            standards_list = list(standards_found)
            if len(standards_list) == 1:
                return standards_list[0]
            elif len(standards_list) <= 3:
                return " og ".join(standards_list)
            else:
                return f"{standards_list[0]} og {len(standards_list)-1} andre"
        
        # Fallback til første ord i spørsmål
        words = question.strip().split()
        if words:
            first_words = " ".join(words[:3])
            return first_words if len(first_words) <= 30 else first_words[:27] + "..."
        
        return "Ny chat"
    
    def create_conversation(self, question: str, answer: str) -> str:
        """Opprett ny samtale og returner ID"""
        conversation_id = str(uuid.uuid4())
        title = self.generate_conversation_title(question, answer)
        
        with sqlite3.connect(self.db_path) as conn:
            # Opprett samtale
            conn.execute("""
                INSERT INTO conversations (id, title, created_at, last_message_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (conversation_id, title))
            
            # Legg til første melding
            conn.execute("""
                INSERT INTO messages (conversation_id, question, answer, timestamp)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (conversation_id, question, answer))
        
        return conversation_id
    
    def add_message_to_conversation(self, conversation_id: str, question: str, answer: str):
        """Legg til melding til eksisterende samtale"""
        with sqlite3.connect(self.db_path) as conn:
            # Legg til melding
            conn.execute("""
                INSERT INTO messages (conversation_id, question, answer, timestamp)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (conversation_id, question, answer))
            
            # Oppdater samtale timestamp
            conn.execute("""
                UPDATE conversations 
                SET last_message_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (conversation_id,))
    
    def get_conversation_history(self, limit: int = 50) -> List[Conversation]:
        """Hent samtalehistorikk sortert etter dato"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.last_message_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                GROUP BY c.id, c.title, c.created_at, c.last_message_at
                ORDER BY c.last_message_at DESC
                LIMIT ?
            """, (limit,))
            
            conversations = []
            for row in cursor.fetchall():
                conversations.append(Conversation(
                    id=row[0],
                    title=row[1],
                    created_at=datetime.fromisoformat(row[2]),
                    last_message_at=datetime.fromisoformat(row[3]),
                    message_count=row[4]
                ))
            
            return conversations
    
    def get_conversation_messages(self, conversation_id: str) -> List[Message]:
        """Hent alle meldinger i en samtale"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, conversation_id, question, answer, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id,))
            
            messages = []
            for row in cursor.fetchall():
                messages.append(Message(
                    id=row[0],
                    conversation_id=row[1],
                    question=row[2],
                    answer=row[3],
                    timestamp=datetime.fromisoformat(row[4])
                ))
            
            return messages
    
    def cleanup_old_conversations(self, days: int = 7):
        """Rydd opp gamle samtaler (standard: 7 dager)"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            # Slett gamle meldinger først (foreign key constraint)
            cursor = conn.execute("""
                DELETE FROM messages 
                WHERE conversation_id IN (
                    SELECT id FROM conversations 
                    WHERE last_message_at < ?
                )
            """, (cutoff_date.isoformat(),))
            
            deleted_messages = cursor.rowcount
            
            # Slett gamle samtaler
            cursor = conn.execute("""
                DELETE FROM conversations 
                WHERE last_message_at < ?
            """, (cutoff_date.isoformat(),))
            
            deleted_conversations = cursor.rowcount
            
            return deleted_conversations, deleted_messages
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Hent spesifikk samtale ved ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.last_message_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.id = ?
                GROUP BY c.id, c.title, c.created_at, c.last_message_at
            """, (conversation_id,))
            
            row = cursor.fetchone()
            if row:
                return Conversation(
                    id=row[0],
                    title=row[1],
                    created_at=datetime.fromisoformat(row[2]),
                    last_message_at=datetime.fromisoformat(row[3]),
                    message_count=row[4]
                )
            
            return None

# Global session manager instans
session_manager = SessionManager() 