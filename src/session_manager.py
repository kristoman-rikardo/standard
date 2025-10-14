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
import asyncio

# Import OpenAI for AI-generated titles
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

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
    """Melding objekt"""
    id: int
    conversation_id: str
    question: str
    answer: str
    timestamp: datetime

class SessionManager:
    """Håndterer brukersesjoner og samtalehistorikk"""
    
    def __init__(self, db_path: str = "conversations.db", enable_ai_titles: bool = True):
        self.db_path = db_path
        self.init_database()
        
        # Initialize OpenAI client for AI-generated titles
        self.openai_client = None
        self.ai_titles_enabled = False
        self.enable_ai_titles = enable_ai_titles  # Konfigurasjon for AI-titler
        self.title_cache = {}  # Cache for AI-genererte titler
        
        if OPENAI_AVAILABLE and enable_ai_titles:
            try:
                openai_key = os.getenv("OPENAI_API_KEY")
                if openai_key:
                    self.openai_client = AsyncOpenAI(api_key=openai_key)
                    self.ai_titles_enabled = True
                    print("✅ AI-genererte titler aktivert")
                else:
                    print("⚠️ OPENAI_API_KEY ikke funnet - bruker regelbaserte titler")
            except Exception as e:
                print(f"⚠️ Kunne ikke initialisere OpenAI for titler: {e}")
        else:
            if not enable_ai_titles:
                print("🔧 AI-titler deaktivert via konfigurasjon")
            else:
                print("⚠️ OpenAI ikke tilgjengelig - bruker regelbaserte titler")
    
    def _connect(self):
        """Get a SQLite connection configured for concurrency (WAL)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        return conn
    
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
            
            # Migrate: add user_id columns if missing
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE messages ADD COLUMN user_id TEXT")
            except Exception:
                pass
            
            # Helpful indexes for user scoping
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, last_message_at DESC)")
            except Exception:
                pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(conversation_id, user_id, timestamp DESC)")
            except Exception:
                pass
    
    async def generate_ai_title(self, question: str, answer: str) -> Optional[str]:
        """Generer intelligent tittel ved hjelp av OpenAI med caching og optimalisering"""
        if not self.ai_titles_enabled or not self.openai_client:
            return None
        
        # Simpel cache basert på spørsmålshash
        cache_key = hash(question[:100])  # Bruk første 100 tegn for caching
        if cache_key in self.title_cache:
            cached_title = self.title_cache[cache_key]
            print(f"🔄 Bruker cached AI-tittel: {cached_title}")
            return cached_title
        
        try:
            # Optimalisert innhold for å spare tokens
            question_preview = question[:150] if question else ""
            answer_preview = answer[:200] if answer else ""
            
            # Forbedret prompt med mer spesifikke instruksjoner
            prompt = f"""Lag en kort, presis tittel for denne samtalen om norske standarder.

Spørsmål: {question_preview}
Svar: {answer_preview}

Tittelkrav:
- Maksimum 4-5 ord på norsk
- Hvis standardnummer nevnes (NS-EN, ISO, TEK), start med det
- Ellers beskriv hovedtemaet konkret
- Unngå: "spørsmål", "om", "informasjon", "hjelp"

Gode eksempler:
- "NS-EN 1090 stålkonstruksjoner"
- "Brannkrav kontorbygg"
- "ISO 9001 kvalitetsstyring"
- "Ventilasjon boligkrav"

Tittel:"""
            
            response = await self.openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=25,  # Redusert for kortere titler
                temperature=0.2,  # Lavere for mer konsistente resultater
                timeout=8  # Redusert timeout
            )
            
            if response.choices and response.choices[0].message.content:
                title = response.choices[0].message.content.strip()
                
                # Forbedret tittelrensing
                title = title.replace('"', '').replace("'", "").replace(':', '').strip()
                
                # Fjern innledende fraser som kan ha sluppet gjennom
                unwanted_starts = ['tittel:', 'svar:', 'for å', 'denne']
                for start in unwanted_starts:
                    if title.lower().startswith(start):
                        title = title[len(start):].strip()
                
                # Sørg for rimelig lengde
                if len(title) > 45:
                    title = title[:42] + "..."
                
                if title and len(title) > 3:
                    # Cache resultatet
                    self.title_cache[cache_key] = title
                    return title
                
        except asyncio.TimeoutError:
            print("⚠️ AI tittel timeout (8s) - bruker fallback")
            return None
        except Exception as e:
            print(f"⚠️ AI tittel feil: {e}")
            return None
        
        return None

    def extract_standards_improved(self, question: str, answer: str) -> List[str]:
        """Forbedret standarddeteksjon med flere mønstre"""
        # Utvidede regex-mønstre for norske og internasjonale standarder
        patterns = [
            r'\b(NS[\s\-]?EN[\s\-]?[0-9A-Z\-\:\+]+)\b',  # NS-EN standarder
            r'\b(EN[\s\-]?[0-9A-Z\-\:\+]+)\b',           # EN standarder
            r'\b(ISO[\s\-]?[0-9A-Z\-\:\+]+)\b',          # ISO standarder
            r'\b(IEC[\s\-]?[0-9A-Z\-\:\+]+)\b',          # IEC standarder
            r'\b(NORSOK[\s\-]?[A-Z0-9\-]+)\b',           # NORSOK standarder
            r'\b(TEK[\s\-]?[0-9]+)\b',                    # TEK forskrifter
            r'\b(NS[\s\-]?[0-9A-Z\-\:\+]+)\b',           # NS standarder
        ]
        
        standards_found = set()
        combined_text = (question + " " + answer).upper()
        
        for pattern in patterns:
            matches = re.findall(pattern, combined_text)
            standards_found.update(matches[:3])  # Maks 3 standarder
            
        return list(standards_found)

    def analyze_content_for_topic(self, question: str) -> Optional[str]:
        """Analyser innhold for å identifisere hovedtema"""
        
        # Definer tema-kategorier med nøkkelord
        topics = {
            'brann': ['brann', 'røykdetektør', 'sprinkler', 'evakuering', 'flukt', 'røykkontroll'],
            'bygg': ['bygg', 'konstruksjon', 'betong', 'stål', 'fundament', 'byggetegning'],
            'elektrisk': ['elektrisk', 'kabel', 'installasjon', 'el-anlegg', 'strøm', 'ledning'],
            'miljø': ['miljø', 'utslipp', 'avfall', 'forurensning', 'klima', 'energi'],
            'kvalitet': ['kvalitet', 'kontroll', 'sertifisering', 'testing', 'godkjenning'],
            'ventilasjon': ['ventilasjon', 'luft', 'klima', 'vifter', 'kanaler'],
            'isolasjon': ['isolasjon', 'isolering', 'varme', 'kulde', 'energi'],
            'sikkerhet': ['sikkerhet', 'vern', 'beskyttelse', 'risiko', 'fare']
        }
        
        question_lower = question.lower()
        
        # Tell treff for hvert tema
        topic_scores = {}
        for topic, keywords in topics.items():
            score = sum(1 for keyword in keywords if keyword in question_lower)
            if score > 0:
                topic_scores[topic] = score
        
        # Returner mest relevante tema
        if topic_scores:
            best_topic = max(topic_scores, key=topic_scores.get)
            return best_topic
            
        return None

    def create_descriptive_fallback(self, question: str) -> str:
        """Lag beskrivende fallback-tittel basert på spørsmål"""
        
        # Fjern vanlige stoppord og normaliser
        stop_words = {
            'hva', 'hvor', 'når', 'hvordan', 'kan', 'du', 'jeg', 'er', 'om', 
            'den', 'det', 'og', 'i', 'på', 'til', 'for', 'med', 'av', 'skal',
            'vil', 'være', 'har', 'som', 'en', 'et', 'de', 'seg', 'ikke'
        }
        
        words = [w for w in question.lower().split() if w not in stop_words and len(w) > 2]
        
        # Prioriter tekniske termer og substantiver
        important_words = []
        for word in words[:8]:  # Sjekk de første 8 relevante ordene
            # Behold ord som inneholder tall, er store bokstaver, eller er lange
            if (any(char.isdigit() for char in word) or 
                word.isupper() or 
                len(word) > 4 or
                word in ['standard', 'krav', 'regel', 'norm', 'forskrift']):
                important_words.append(word.title())
        
        if important_words:
            title = " ".join(important_words[:4])  # Maks 4 ord
            return title if len(title) <= 40 else title[:37] + "..."
        
        # Siste fallback - bare de første ordene
        if words:
            title = " ".join(words[:3]).title()
            return title if len(title) <= 30 else title[:27] + "..."
            
        return "Ny samtale"

    def generate_conversation_title_improved(self, question: str, answer: str) -> str:
        """Forbedret tittelgenerering med AI og intelligent fallback"""
        
        # 1. Prøv AI-generering først hvis tilgjengelig
        if self.ai_titles_enabled:
            try:
                # Kjør AI-tittelgenerering synkront med kortere timeout
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ai_title = loop.run_until_complete(
                        asyncio.wait_for(self.generate_ai_title(question, answer), timeout=12)
                    )
                    if ai_title and len(ai_title.strip()) > 3:
                        print(f"✅ AI-generert tittel: {ai_title}")
                        return ai_title
                finally:
                    loop.close()
            except asyncio.TimeoutError:
                print("⚠️ AI-tittel timeout (12s) - bruker fallback")
            except Exception as e:
                print(f"⚠️ AI-tittel feil: {e}")

        # 2. Prøv forbedret standarddeteksjon
        standards = self.extract_standards_improved(question, answer)
        if standards:
            topic = self.analyze_content_for_topic(question)
            if topic and len(standards) == 1:
                return f"{standards[0]} - {topic}"
            elif len(standards) == 1:
                return standards[0]
            elif len(standards) <= 3:
                return " og ".join(standards[:2])  # Vis maks 2 for lesbarhet
            else:
                return f"{standards[0]} og {len(standards)-1} andre"

        # 3. Bruk temabasert tittel
        topic = self.analyze_content_for_topic(question)
        if topic:
            return f"Spørsmål om {topic}"

        # 4. Forbedret fallback basert på innhold
        descriptive_title = self.create_descriptive_fallback(question)
        if descriptive_title != "Ny samtale":
            return descriptive_title

        # 5. Siste fallback - original logikk
        return self.generate_conversation_title(question, answer)
    
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
    
    def create_conversation(self, question: str, answer: str, user_id: str) -> str:
        """Opprett ny samtale og returner ID for gitt bruker"""
        conversation_id = str(uuid.uuid4())
        title = self.generate_conversation_title_improved(question, answer)
        
        with self._connect() as conn:
            # Opprett samtale
            conn.execute("""
                INSERT INTO conversations (id, title, created_at, last_message_at, user_id)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """, (conversation_id, title, user_id))
            
            # Legg til første melding
            conn.execute("""
                INSERT INTO messages (conversation_id, question, answer, timestamp, user_id)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """, (conversation_id, question, answer, user_id))
        
        return conversation_id
    
    def create_placeholder_conversation(self, user_id: str) -> str:
        """Opprett en placeholder-samtale for gitt bruker"""
        conversation_id = str(uuid.uuid4())
        title = "Ny samtale"
        
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO conversations (id, title, created_at, last_message_at, user_id)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """, (conversation_id, title, user_id))
        
        print(f"✅ Created placeholder conversation for user {user_id}: {conversation_id}")
        return conversation_id
    
    def add_message_to_conversation(self, conversation_id: str, question: str, answer: str, user_id: str):
        """Legg til melding til eksisterende samtale for gitt bruker"""
        with self._connect() as conn:
            # Verify conversation ownership
            cur = conn.execute("SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
            if not cur.fetchone():
                raise ValueError("Conversation not found or access denied")
            
            # Sjekk om dette er første melding i samtalen
            cursor = conn.execute("""
                SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND user_id = ?
            """, (conversation_id, user_id))
            message_count = cursor.fetchone()[0]
            
            # Legg til melding
            conn.execute("""
                INSERT INTO messages (conversation_id, question, answer, timestamp, user_id)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """, (conversation_id, question, answer, user_id))
            
            # Hvis dette er første melding, oppdater tittelen fra "Ny samtale" til en riktig tittel
            if message_count == 0:
                new_title = self.generate_conversation_title_improved(question, answer)
                conn.execute("""
                    UPDATE conversations 
                    SET title = ?, last_message_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                """, (new_title, conversation_id, user_id))
                print(f"✅ Updated conversation title from 'Ny samtale' to '{new_title}' for {conversation_id}")
            else:
                # Bare oppdater timestamp
                conn.execute("""
                    UPDATE conversations 
                    SET last_message_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                """, (conversation_id, user_id))
    
    def add_to_conversation(self, conversation_id: str, question: str, answer: str, user_id: str):
        """Alias for add_message_to_conversation med user-scope"""
        return self.add_message_to_conversation(conversation_id, question, answer, user_id)
    
    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation and all its messages for the given user"""
        try:
            with self._connect() as conn:
                # Ensure ownership
                cur = conn.execute("SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
                if not cur.fetchone():
                    print(f"⚠️ Conversation {conversation_id} not found or not owned by user")
                    return False
                
                # Delete all messages in the conversation for this user
                conn.execute("DELETE FROM messages WHERE conversation_id = ? AND user_id = ?", (conversation_id, user_id))
                
                # Delete the conversation
                cursor = conn.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
                
                if cursor.rowcount > 0:
                    print(f"✅ Deleted conversation {conversation_id} for user {user_id}")
                    return True
                else:
                    print(f"⚠️ Conversation {conversation_id} not found for user {user_id}")
                    return False
        except Exception as e:
            print(f"❌ Error deleting conversation {conversation_id}: {e}")
            return False
    
    def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Conversation]:
        """Hent samtalehistorikk sortert etter dato for gitt bruker"""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.last_message_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id AND m.user_id = c.user_id
                WHERE c.user_id = ?
                GROUP BY c.id, c.title, c.created_at, c.last_message_at
                ORDER BY c.last_message_at DESC
                LIMIT ?
            """, (user_id, limit))
            
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
    
    def get_conversation_messages(self, conversation_id: str, user_id: str) -> List[Message]:
        """Hent alle meldinger i en samtale for gitt bruker"""
        with self._connect() as conn:
            # Ensure ownership
            cur = conn.execute("SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
            if not cur.fetchone():
                return []
            
            cursor = conn.execute("""
                SELECT id, conversation_id, question, answer, timestamp
                FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id, user_id))
            
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
        
        with self._connect() as conn:
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
    
    def get_conversation_by_id(self, conversation_id: str, user_id: str) -> Optional[Conversation]:
        """Hent spesifikk samtale ved ID for gitt bruker"""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.last_message_at, COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id AND m.user_id = c.user_id
                WHERE c.id = ? AND c.user_id = ?
                GROUP BY c.id, c.title, c.created_at, c.last_message_at
            """, (conversation_id, user_id))
            
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

    def clear_title_cache(self):
        """Tøm cache for AI-genererte titler"""
        self.title_cache.clear()
        print("🧹 Title cache cleared")
    
    def get_title_cache_stats(self):
        """Hent statistikk for title cache"""
        return {
            "cached_titles": len(self.title_cache),
            "cache_keys": list(self.title_cache.keys())[:10]  # Vis bare første 10
        }
    
    async def update_conversation_title_ai(self, conversation_id: str) -> bool:
        """Oppdater en eksisterende samtale med AI-generert tittel"""
        if not self.ai_titles_enabled:
            print("⚠️ AI-titler ikke aktivert")
            return False
        
        try:
            # Hent første melding i samtalen
            # Merk: Dette krever også user_id i praksis; denne metoden brukes ikke i offentlige endepunkt
            messages = self.get_conversation_messages(conversation_id, user_id="__internal__")
            if not messages:
                print("⚠️ Ingen meldinger funnet for samtale")
                return False
            
            first_message = messages[0]
            
            # Generer ny AI-tittel
            new_title = await self.generate_ai_title(first_message.question, first_message.answer)
            
            if new_title:
                # Oppdater tittelen i databasen (uten bruker-sjekk for intern bruk)
                with self._connect() as conn:
                    conn.execute("""
                        UPDATE conversations 
                        SET title = ?
                        WHERE id = ?
                    """, (new_title, conversation_id))
                
                print(f"✅ Oppdatert tittel for {conversation_id}: '{new_title}'")
                return True
            else:
                print("⚠️ Kunne ikke generere AI-tittel for eksisterende samtale")
                return False
                
        except Exception as e:
            print(f"❌ Feil ved oppdatering av samtale-tittel: {e}")
            return False
    
    def update_all_conversation_titles(self, limit: int = 10) -> Dict:
        """Oppdater titler for de siste samtalene med AI-genererte titler"""
        if not self.ai_titles_enabled:
            return {"error": "AI-titler ikke aktivert"}
        
        # Denne funksjonen beholdes uendret for enkelhets skyld
        conversations = self.get_conversation_history(user_id="__internal__", limit=limit)
        results = {"updated": 0, "failed": 0, "skipped": 0}
        
        print(f"🔄 Oppdaterer titler for {len(conversations)} samtaler...")
        
        for conv in conversations:
            try:
                # Skip if title already looks AI-generated (not just standard numbers)
                if (len(conv.title.split()) >= 3 and 
                    not conv.title.startswith(('NS-', 'EN ', 'ISO ', 'IEC ')) and
                    'chat' not in conv.title.lower()):
                    print(f"⏭️ Hopper over: '{conv.title}' (ser allerede bra ut)")
                    results["skipped"] += 1
                    continue
                
                # Run async update in a new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    success = loop.run_until_complete(
                        asyncio.wait_for(self.update_conversation_title_ai(conv.id), timeout=15)
                    )
                    if success:
                        results["updated"] += 1
                    else:
                        results["failed"] += 1
                finally:
                    loop.close()
                    
            except Exception as e:
                print(f"❌ Feil ved oppdatering av {conv.id}: {e}")
                results["failed"] += 1
        
        print(f"✅ Oppdatering fullført: {results['updated']} oppdatert, {results['failed']} feilet, {results['skipped']} hoppet over")
        return results

# Global session manager instans med AI-titler aktivert
session_manager = SessionManager(enable_ai_titles=True) 