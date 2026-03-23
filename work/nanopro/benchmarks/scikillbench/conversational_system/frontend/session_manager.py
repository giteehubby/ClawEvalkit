"""
Session Manager for Multi-Turn Conversations

Manages conversation state using OpenAI Agents SDK's Session functionality.
Handles:
- Multi-turn dialogue history
- Current solution tracking (for improvement scenarios)
- User feedback status
- Timeout management (5 minutes without response)
"""

from __future__ import annotations

import os
import time
import asyncio
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from agents import Runner, SQLiteSession

# Import MLflow for tracing
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


# Global cache to track which databases have been checked/migrated
_MIGRATED_DATABASES = set()


def _ensure_saved_conversations_schema(db_path: str) -> bool:
    """
    Ensure the database has the saved conversations schema.

    This function checks if the required columns (is_saved, custom_title, notes)
    exist in the agent_sessions table. If not, it adds them automatically.

    This is called automatically when creating a ConversationSessionManager,
    so users don't need to run a separate migration script.

    Args:
        db_path: Path to the SQLite database

    Returns:
        True if schema is correct (or was successfully migrated), False on error
    """
    # Check if we've already migrated this database in this session
    if db_path in _MIGRATED_DATABASES:
        return True

    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_sessions'")
        if not cursor.fetchone():
            # Table doesn't exist yet - it will be created when user starts first conversation
            conn.close()
            return True

        # Check existing columns
        cursor.execute("PRAGMA table_info(agent_sessions)")
        existing_columns = [col[1] for col in cursor.fetchall()]

        # Define required columns for saved conversations feature
        required_columns = {
            'is_saved': 'INTEGER DEFAULT 0',
            'custom_title': 'TEXT',
            'notes': 'TEXT'
        }

        # Add missing columns
        migrations_performed = []
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                alter_query = f"ALTER TABLE agent_sessions ADD COLUMN {column_name} {column_type}"
                cursor.execute(alter_query)
                migrations_performed.append(column_name)

        conn.commit()
        conn.close()

        # Log migration if any columns were added
        if migrations_performed:
            print(f"✓ Database schema updated: added {', '.join(migrations_performed)} columns")

        # Mark this database as migrated
        _MIGRATED_DATABASES.add(db_path)
        return True

    except Exception as e:
        print(f"⚠️  Warning: Could not ensure saved conversations schema: {e}")
        return False


class ConversationSessionManager:
    """
    Manages state for a multi-turn conversation with a user.

    Uses SQLiteSession from OpenAI Agents SDK to automatically maintain
    conversation history across multiple agent runs.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        db_path: str = "conversations.db",
        load_existing: bool = False
    ):
        """
        Initialize conversation session.

        Args:
            session_id: Unique identifier for this conversation session
            user_id: User identifier (from authentication)
            db_path: Path to SQLite database for storing sessions
            load_existing: If True, load an existing session; if False, create new session with timestamp
        """
        self.session_id = session_id
        self.user_id = user_id
        self.db_path = db_path

        # Ensure database has saved conversations schema (auto-migration)
        _ensure_saved_conversations_schema(db_path)

        # Create SQLiteSession - automatically manages conversation history
        # If load_existing=True, uses session_id as-is (for resuming sessions)
        # If load_existing=False, session_id should already include timestamp
        self.session = SQLiteSession(
            session_id=session_id,
            db_path=db_path
        )

        # Conversation state
        self.last_activity = time.time()
        self.current_solution = None  # Stores current solution for improvement
        self.waiting_for_feedback = False
        self.feedback_received = None
        self.original_query = None  # Track the original user query before any improvements

        print(f"📝 Session {session_id} created for user {user_id}")

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def get_idle_time(self) -> float:
        """
        Get time elapsed since last activity in seconds.

        Returns:
            Seconds since last activity
        """
        return time.time() - self.last_activity

    def is_timeout(self, timeout_seconds: int = 300) -> bool:
        """
        Check if session has timed out.

        Args:
            timeout_seconds: Timeout duration (default 300 = 5 minutes)

        Returns:
            True if session has timed out
        """
        return self.get_idle_time() > timeout_seconds

    async def run_conversation_turn(
        self,
        orchestrator,
        user_message: str
    ) -> Any:
        """
        Execute one turn of conversation with the Orchestrator.

        The session automatically includes full conversation history,
        so the agent has context from previous turns.

        IMPORTANT: This method injects the user_id at the beginning of each message
        so that the Orchestrator can pass it to tools that require user_id
        (like search_memory, solve_with_deep_solver, save_to_memory).

        Args:
            orchestrator: The Orchestrator agent
            user_message: User's message/question

        Returns:
            Agent run result
        """
        # Update activity timestamp
        self.update_activity()

        # Inject user_id and critical reminders at the beginning of the message
        # This allows the Orchestrator to extract user_id and pass it to tools
        # The reminders reinforce critical workflow steps without being saved to original query
        full_message = (
            f"[SYSTEM: user_id={self.user_id}]\n"
            f"[CRITICAL REMINDER: 1) FIRST call search_memory(query, user_id). "
            f"2) If the problem needs online search/deepresearch, documentation lookup, or investigation → use solve_with_deep_solver(query, user_id) which has dedicated research agents with online search capabilities. "
            f"3) Only skip solve_with_deep_solver if: problem is very simple or you have working memory solution, AND you are 100% confident that you can solve it without any research.]\n"
            f"{user_message}"
        )

        print(f"\n💬 User: {user_message[:100]}...")

        turn_start = time.time()

        # Use MLflow run - let autolog automatically create spans
        # DO NOT create manual spans - they interfere with autolog's trace hierarchy
        if MLFLOW_AVAILABLE:
            run_name = f"conversation_turn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            with mlflow.start_run(run_name=run_name):
                # Log parameters
                mlflow.log_param("session_id", self.session_id)
                mlflow.log_param("user_id", self.user_id)
                mlflow.log_param("message_length", len(user_message))
                mlflow.log_param("user_message_preview", user_message[:500] + "..." if len(user_message) > 500 else user_message)

                try:
                    # Run orchestrator - autolog will automatically create "AgentRunner.run" span
                    # and capture all agent/tool/LLM spans in proper hierarchy
                    runner = Runner()
                    result = await runner.run(
                        orchestrator,
                        full_message,
                        session=self.session,
                        max_turns=5000
                    )

                    # Update activity after response
                    self.update_activity()

                    turn_time = time.time() - turn_start
                    print(f"🤖 Orchestrator responded")

                    # Extract response text
                    response_text = str(result.final_output) if hasattr(result, 'final_output') else str(result)

                    # Log metrics to the run
                    mlflow.log_metric("execution_time_seconds", turn_time)
                    mlflow.log_metric("response_length", len(response_text))
                    mlflow.log_param("success", True)

                    return result

                except Exception as e:
                    turn_time = time.time() - turn_start
                    print(f"❌ Orchestrator error: {str(e)}")

                    # Log error metrics
                    mlflow.log_metric("execution_time_seconds", turn_time)
                    mlflow.log_param("success", False)
                    mlflow.log_param("error_type", type(e).__name__)
                    mlflow.log_param("error_message", str(e))

                    raise
        else:
            # No MLflow - just run normally
            runner = Runner()
            result = await runner.run(
                orchestrator,
                full_message,
                session=self.session,
                max_turns=5000
            )
            self.update_activity()
            return result

    def store_current_solution(self, solution_data: Dict[str, Any]):
        """
        Store the current solution for potential improvement.

        Called after Orchestrator returns a solution.
        This allows user to request improvements based on current code.

        Args:
            solution_data: Dictionary containing:
                - final_code: The working code
                - explanation: Explanation of solution
                - execution_results: Raw execution output
        """
        self.current_solution = {
            "code": solution_data.get("final_code", ""),
            "explanation": solution_data.get("explanation", ""),
            "results": solution_data.get("execution_results", ""),
            "timestamp": datetime.now().isoformat()
        }
        self.waiting_for_feedback = True

        print("💾 Current solution stored for potential improvement")

    def get_current_solution_code(self) -> Optional[str]:
        """
        Get current solution code for improvement scenarios.

        Returns:
            Current solution code, or None if no solution stored
        """
        if self.current_solution:
            return self.current_solution.get("code")
        return None

    def set_original_query(self, query: str):
        """
        Set the original user query at the start of a problem-solving session.

        This should be called when user first asks a question.
        It will NOT be updated during improvement iterations.

        Args:
            query: The original user query
        """
        if self.original_query is None:
            self.original_query = query
            print(f"📌 Original query set: {query[:50]}...")

    def get_original_query(self) -> Optional[str]:
        """
        Get the original user query.

        Returns:
            Original query, or None if not set
        """
        return self.original_query

    def append_to_original_query(self, additional_context: str):
        """
        Append additional context to the original query.

        Used when user clicks "Continue" to add supplementary details
        to the original problem.

        Args:
            additional_context: Additional details to append
        """
        if self.original_query is not None:
            # Append with a clear separator
            self.original_query = f"{self.original_query}; {additional_context}"
            print(f"📝 Updated original query: {self.original_query[:100]}...")
        else:
            # If no original query exists, set it as the query
            self.original_query = additional_context
            print(f"📌 Original query set: {additional_context[:50]}...")

    def set_feedback(
        self,
        feedback_type: Literal["satisfied", "improve", "exit"]
    ):
        """
        Record user feedback on current solution.

        Args:
            feedback_type: Type of feedback
                - "satisfied": User is happy, save to memory
                - "improve": User wants improvements
                - "exit": User wants to stop
        """
        self.feedback_received = feedback_type
        self.waiting_for_feedback = False
        self.update_activity()

        print(f"📊 User feedback: {feedback_type}")

    def clear_feedback(self):
        """Clear feedback status after processing."""
        self.feedback_received = None
        self.waiting_for_feedback = False

    def reset_for_new_query(self):
        """
        Reset state for a new query.

        Called after feedback is processed and moving to next question.
        """
        self.current_solution = None
        self.original_query = None  # Clear original query for next problem
        self.clear_feedback()
        self.update_activity()

    async def wait_for_feedback(
        self,
        timeout_seconds: int = 300,
        check_interval: float = 1.0
    ) -> Literal["satisfied", "improve", "exit", "timeout"]:
        """
        Wait for user feedback with timeout.

        Args:
            timeout_seconds: Timeout duration (default 300 = 5 minutes)
            check_interval: How often to check for feedback in seconds

        Returns:
            Feedback type or "timeout"
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout_seconds:
            # Check if feedback received
            if self.feedback_received:
                return self.feedback_received

            # Wait before next check
            await asyncio.sleep(check_interval)

        # Timeout reached
        print("⏱️ Feedback timeout - 5 minutes elapsed")
        return "timeout"

    def clear_session(self):
        """
        Clear the conversation history.

        Useful for starting fresh or after logout.
        """
        self.session.clear_session()
        self.reset_for_new_query()
        print("🗑️ Session history cleared")

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get information about current session.

        Returns:
            Dictionary with session metadata
        """
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "idle_time": self.get_idle_time(),
            "is_timeout": self.is_timeout(),
            "waiting_for_feedback": self.waiting_for_feedback,
            "has_current_solution": self.current_solution is not None
        }

    async def export_conversation_history(self) -> str:
        """
        Export the conversation history as Markdown.

        Returns:
            Markdown-formatted conversation history as string
        """
        try:
            # Get all conversation items from session (async method)
            items = await self.session.get_items()
            return self._export_as_markdown(items)

        except Exception as e:
            print(f"Error exporting conversation: {e}")
            return f"Error exporting conversation: {str(e)}"

    def _export_as_markdown(self, items: list) -> str:
        """
        Format conversation items as Markdown.

        Args:
            items: List of conversation items from SQLiteSession

        Returns:
            Markdown-formatted string
        """
        lines = []

        # Header
        lines.append("# 💬 Conversation History")
        lines.append("")
        lines.append(f"> **Session:** `{self.session_id}`")
        lines.append(f"> **User:** `{self.user_id}`")
        lines.append(f"> **Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        if not items:
            lines.append("*No conversation history available.*")
            return "\n".join(lines)

        # Process conversation items
        for i, item in enumerate(items, 1):
            role = item.get("role", "unknown")
            content = item.get("content", "")

            # Format based on role
            if role == "user":
                lines.append("")
                lines.append(f"### 👤 User")
                lines.append("")
                lines.append(f"> {content}")
                lines.append("")

            elif role == "assistant":
                lines.append("")
                lines.append(f"### 🤖 Assistant")
                lines.append("")

                # Parse content to extract code and results if present
                content_str = str(content)

                # Check if content has multiple sections (code, results)
                if "```" in content_str:
                    # Content has code blocks, preserve them
                    lines.append(content_str)
                else:
                    # Regular text content
                    lines.append(content_str)

                lines.append("")
                lines.append("---")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("<div align='center'>")
        lines.append("<i>Generated by CASCADE</i>")
        lines.append("</div>")

        return "\n".join(lines)

    @staticmethod
    def list_user_sessions(user_id: str, db_path: str = "conversations.db", limit: int = 20):
        """
        List all sessions for a given user.

        Args:
            user_id: User identifier
            db_path: Path to SQLite database
            limit: Maximum number of sessions to return

        Returns:
            List of tuples: [(session_id, created_at, updated_at), ...]
            Ordered by updated_at DESC (most recent first)
        """
        import sqlite3

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query sessions that belong to this user (session_id contains user_id)
            query = """
                SELECT session_id, created_at, updated_at
                FROM agent_sessions
                WHERE session_id LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """

            cursor.execute(query, (f"session_{user_id}%", limit))
            sessions = cursor.fetchall()

            conn.close()
            return sessions

        except Exception as e:
            print(f"Error listing sessions: {e}")
            return []

    @staticmethod
    def get_session_preview(session_id: str, db_path: str = "conversations.db"):
        """
        Get preview information for a session.

        Args:
            session_id: Session identifier
            db_path: Path to SQLite database

        Returns:
            Tuple: (preview_text, message_count)
            preview_text: First user message (max 50 chars)
            message_count: Total number of messages in session
        """
        import sqlite3
        import json

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get all messages for this session
            query = """
                SELECT message_data
                FROM agent_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
            """

            cursor.execute(query, (session_id,))
            messages = cursor.fetchall()

            conn.close()

            if not messages:
                return ("Empty session", 0)

            # Find first user message for preview
            preview_text = "Session"
            for msg_data in messages:
                try:
                    msg = json.loads(msg_data[0])
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        # Remove system tags like [SYSTEM: user_id=...] and [CRITICAL REMINDER:...]
                        if "[SYSTEM:" in content:
                            content = content.split("\n", 2)[-1]  # Take text after system lines
                        if "[CRITICAL REMINDER:" in content:
                            content = content.split("\n", 2)[-1]

                        preview_text = content.strip()[:50]
                        break
                except:
                    continue

            return (preview_text, len(messages))

        except Exception as e:
            print(f"Error getting session preview: {e}")
            return ("Error loading preview", 0)

    @staticmethod
    def load_session_messages(session_id: str, db_path: str = "conversations.db"):
        """
        Load all messages from a session in Streamlit format.

        Args:
            session_id: Session identifier
            db_path: Path to SQLite database

        Returns:
            List of message dicts: [{"role": "user/assistant", "content": "...", ...}, ...]
        """
        import sqlite3
        import json

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get all messages for this session
            query = """
                SELECT message_data
                FROM agent_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
            """

            cursor.execute(query, (session_id,))
            messages = cursor.fetchall()

            conn.close()

            # Parse and format messages for Streamlit
            formatted_messages = []
            for msg_data in messages:
                try:
                    msg = json.loads(msg_data[0])
                    role = msg.get("role")
                    content = msg.get("content", "")

                    # Skip messages with invalid or missing role
                    if not role or role not in ["user", "assistant"]:
                        continue

                    # Handle content that might be a list (from agent responses)
                    if isinstance(content, list):
                        # Extract text from list of dicts (agent response format)
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict):
                                if "text" in item:
                                    text_parts.append(str(item["text"]))
                            else:
                                text_parts.append(str(item))
                        content = "\n".join(text_parts) if text_parts else ""

                    # Convert to string if not already
                    content = str(content) if content else ""

                    # Skip empty messages
                    if not content.strip():
                        continue

                    # Clean up system tags from user messages
                    if role == "user":
                        # Remove [SYSTEM: user_id=...] and [CRITICAL REMINDER:...] lines
                        lines = content.split("\n")
                        cleaned_lines = []
                        for line in lines:
                            if not line.startswith("[SYSTEM:") and not line.startswith("[CRITICAL REMINDER:") and not line.startswith("[ORIGINAL_QUERY:"):
                                cleaned_lines.append(line)
                        content = "\n".join(cleaned_lines).strip()

                    # Skip if content is now empty after cleaning
                    if not content:
                        continue

                    formatted_messages.append({
                        "role": role,
                        "content": content
                    })

                except Exception as e:
                    print(f"Error parsing message: {e}")
                    continue

            return formatted_messages

        except Exception as e:
            print(f"Error loading session messages: {e}")
            return []

    @staticmethod
    def toggle_saved_status(session_id: str, is_saved: bool, db_path: str = "conversations.db"):
        """
        Toggle the saved status of a session.

        Args:
            session_id: Session identifier
            is_saved: True to mark as saved, False to unsave
            db_path: Path to SQLite database

        Returns:
            True if successful, False otherwise
        """
        import sqlite3

        # Ensure schema has required columns
        _ensure_saved_conversations_schema(db_path)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Update the is_saved flag
            query = """
                UPDATE agent_sessions
                SET is_saved = ?
                WHERE session_id = ?
            """

            cursor.execute(query, (1 if is_saved else 0, session_id))
            conn.commit()
            conn.close()

            print(f"{'💾' if is_saved else '📤'} Session {session_id[:8]}... {'saved' if is_saved else 'unsaved'}")
            return True

        except Exception as e:
            print(f"Error toggling saved status: {e}")
            return False

    @staticmethod
    def set_session_metadata(
        session_id: str,
        custom_title: Optional[str] = None,
        notes: Optional[str] = None,
        db_path: str = "conversations.db"
    ):
        """
        Set custom title and notes for a session.

        Args:
            session_id: Session identifier
            custom_title: Custom title for the session (can be empty string to clear)
            notes: Notes/description for the session (can be empty string to clear)
            db_path: Path to SQLite database

        Returns:
            True if successful, False otherwise
        """
        import sqlite3

        # Ensure schema has required columns
        _ensure_saved_conversations_schema(db_path)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Build update query dynamically based on what's provided
            # Now we check for None (meaning not provided) vs empty string (meaning clear the field)
            updates = []
            params = []

            # Use a sentinel to detect if argument was actually passed
            # If custom_title is not None, it was passed (even if empty string)
            if custom_title is not None:
                updates.append("custom_title = ?")
                # Convert empty string to None in database (NULL)
                params.append(custom_title if custom_title else None)

            if notes is not None:
                updates.append("notes = ?")
                # Convert empty string to None in database (NULL)
                params.append(notes if notes else None)

            if not updates:
                # Nothing to update
                conn.close()
                return True

            params.append(session_id)
            query = f"""
                UPDATE agent_sessions
                SET {', '.join(updates)}
                WHERE session_id = ?
            """

            cursor.execute(query, params)
            conn.commit()
            conn.close()

            print(f"📝 Session metadata updated for {session_id[:8]}...")
            return True

        except Exception as e:
            print(f"Error setting session metadata: {e}")
            return False

    @staticmethod
    def list_saved_sessions(user_id: str, db_path: str = "conversations.db"):
        """
        List all saved sessions for a given user.

        Args:
            user_id: User identifier
            db_path: Path to SQLite database

        Returns:
            List of dicts: [{"session_id": "...", "custom_title": "...", "notes": "...", ...}, ...]
            Ordered by updated_at DESC (most recent first)
        """
        import sqlite3

        # Ensure schema has required columns
        _ensure_saved_conversations_schema(db_path)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query saved sessions that belong to this user
            query = """
                SELECT session_id, created_at, updated_at, custom_title, notes
                FROM agent_sessions
                WHERE session_id LIKE ? AND is_saved = 1
                ORDER BY updated_at DESC
            """

            cursor.execute(query, (f"session_{user_id}%",))
            rows = cursor.fetchall()

            conn.close()

            # Format as list of dicts
            sessions = []
            for row in rows:
                sessions.append({
                    "session_id": row[0],
                    "created_at": row[1],
                    "updated_at": row[2],
                    "custom_title": row[3],
                    "notes": row[4]
                })

            return sessions

        except Exception as e:
            print(f"Error listing saved sessions: {e}")
            return []

    @staticmethod
    def get_session_metadata(session_id: str, db_path: str = "conversations.db"):
        """
        Get metadata for a specific session.

        Args:
            session_id: Session identifier
            db_path: Path to SQLite database

        Returns:
            Dict with metadata: {"is_saved": bool, "custom_title": str, "notes": str}
            Returns None if session not found
        """
        import sqlite3

        # Ensure schema has required columns
        _ensure_saved_conversations_schema(db_path)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            query = """
                SELECT is_saved, custom_title, notes
                FROM agent_sessions
                WHERE session_id = ?
            """

            cursor.execute(query, (session_id,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return {
                    "is_saved": bool(row[0]),
                    "custom_title": row[1],
                    "notes": row[2]
                }
            else:
                return None

        except Exception as e:
            print(f"Error getting session metadata: {e}")
            return None


class SessionRegistry:
    """
    Registry to manage multiple active sessions.

    Useful for tracking sessions across multiple users.
    """

    def __init__(self):
        """Initialize session registry."""
        self.sessions: Dict[str, ConversationSessionManager] = {}

    def create_session(
        self,
        session_id: str,
        user_id: str,
        db_path: str = "conversations.db"
    ) -> ConversationSessionManager:
        """
        Create and register a new session.

        Args:
            session_id: Unique session identifier
            user_id: User identifier
            db_path: Database path

        Returns:
            New ConversationSessionManager instance
        """
        session = ConversationSessionManager(session_id, user_id, db_path)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSessionManager]:
        """
        Get existing session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session manager or None if not found
        """
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str):
        """
        Remove session from registry.

        Args:
            session_id: Session identifier
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            print(f"🗑️ Session {session_id} removed from registry")

    def cleanup_timeout_sessions(self, timeout_seconds: int = 300):
        """
        Remove timed-out sessions from registry.

        Args:
            timeout_seconds: Timeout threshold
        """
        timeout_sessions = [
            sid for sid, session in self.sessions.items()
            if session.is_timeout(timeout_seconds)
        ]

        for sid in timeout_sessions:
            self.remove_session(sid)

        if timeout_sessions:
            print(f"🧹 Cleaned up {len(timeout_sessions)} timed-out sessions")


# Global session registry
_session_registry = SessionRegistry()


def get_session_registry() -> SessionRegistry:
    """Get the global session registry."""
    return _session_registry


# Export
__all__ = [
    'ConversationSessionManager',
    'SessionRegistry',
    'get_session_registry'
]
