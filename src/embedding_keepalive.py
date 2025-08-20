# -*- coding: utf-8 -*-
"""
Keep-alive system for embedding API to prevent cold starts
"""
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional
from src.config import EMBEDDING_API_ENDPOINT, EMBEDDING_KEEPALIVE_ENABLED, EMBEDDING_KEEPALIVE_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

class EmbeddingKeepAlive:
    """Keep-alive service to prevent embedding API cold starts"""
    
    def __init__(self, ping_interval_minutes: int = 10):
        self.ping_interval = timedelta(minutes=ping_interval_minutes)
        self.last_activity = datetime.now()
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
    def update_activity(self):
        """Update last activity timestamp when API is used"""
        self.last_activity = datetime.now()
        
    async def ping_embedding_api(self) -> bool:
        """Send a lightweight ping to the embedding API"""
        if not EMBEDDING_API_ENDPOINT or "127.0.0.1" in EMBEDDING_API_ENDPOINT or "localhost" in EMBEDDING_API_ENDPOINT:
            return True  # Skip for local APIs
            
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # Send minimal ping request
                payload = {"text": "ping"}
                async with session.post(EMBEDDING_API_ENDPOINT, json=payload) as response:
                    if response.status == 200:
                        logger.debug("✅ Embedding API keep-alive ping successful")
                        return True
                    else:
                        logger.warning(f"⚠️ Embedding API ping returned status {response.status}")
                        return False
        except Exception as e:
            logger.warning(f"⚠️ Embedding API keep-alive ping failed: {e}")
            return False
            
    async def keep_alive_loop(self):
        """Main keep-alive loop"""
        logger.info("🔄 Starting embedding API keep-alive service")
        
        while self.running:
            try:
                # Check if we need to ping (no activity for a while)
                time_since_activity = datetime.now() - self.last_activity
                
                if time_since_activity >= self.ping_interval:
                    logger.debug("📡 Sending keep-alive ping to embedding API")
                    await self.ping_embedding_api()
                    self.update_activity()  # Reset activity timer
                
                # Wait before next check (check every minute)
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ Keep-alive loop error: {e}")
                await asyncio.sleep(60)  # Continue despite errors
                
    def start(self):
        """Start the keep-alive service"""
        if not EMBEDDING_KEEPALIVE_ENABLED:
            logger.info("ℹ️ Embedding keep-alive disabled by configuration")
            return
            
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self.keep_alive_loop())
            logger.info("🚀 Embedding API keep-alive service started")
            
    def stop(self):
        """Stop the keep-alive service"""
        if self.running:
            self.running = False
            if self.task:
                self.task.cancel()
            logger.info("🛑 Embedding API keep-alive service stopped")

# Global keep-alive instance
embedding_keepalive = EmbeddingKeepAlive(ping_interval_minutes=EMBEDDING_KEEPALIVE_INTERVAL_MINUTES)
