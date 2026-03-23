"""
Streamlit Frontend for CASCADE (Conversational Materials Science and Chemistry Assistant)

Features:
- User authentication with Supabase
- Multi-turn conversation with memory
- Code display and execution results
- User feedback buttons (Satisfied / Improve / Exit)
- Timeout handling (5 minutes)
- User preferences management (API keys)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables FIRST
# Priority: .env file > shell environment (.bashrc) > code defaults
current_dir = Path(__file__).resolve().parent
conversational_system_dir = current_dir.parent
project_root = conversational_system_dir.parent
sys.path.insert(0, str(project_root))
env_path = project_root / '.env'
load_dotenv(env_path, override=True)

# Database path for conversation history (can be overridden via environment variable)
CONVERSATIONS_DB_PATH = os.getenv(
    "CONVERSATIONS_DB_PATH",
    str(conversational_system_dir / "conversations.db")
)

# Clean up temp_code directory ONLY on first startup (not on every Streamlit re-run)
# Use environment variable to track if cleanup has been done this session
if not os.getenv("_TEMP_CODE_CLEANED"):
    temp_code_dir = conversational_system_dir / "temp_code"
    if temp_code_dir.exists():
        import shutil
        for item in temp_code_dir.iterdir():
            if item.name != ".gitkeep":
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
        print(f"🧹 Cleaned up temp_code directory: {temp_code_dir}")
    os.environ["_TEMP_CODE_CLEANED"] = "1"

# Now import other modules
import asyncio
import streamlit as st
from datetime import datetime
import supabase
from supabase import create_client, Client

# Initialize MLflow tracing for the conversational system
try:
    import mlflow
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
    mlflow.set_tracking_uri(mlflow_uri)
    # NOTE: log_traces=True is required for both individual API calls AND agent traces
    # Individual traces (embedding/completion) can be filtered out in the UI or via queries
    mlflow.openai.autolog(disable=False, log_traces=True)
    mlflow.tracing.enable()
    mlflow.set_experiment("conversational_system")
    print(f"✅ MLflow tracing enabled at {mlflow_uri}")
except Exception as e:
    print(f"⚠️  MLflow tracing not available: {e}")

# Import our components
from conversational_system.core.orchestrator import create_orchestrator
from conversational_system.core.deep_solver import solve_with_deep_solver
from conversational_system.frontend.session_manager import (
    ConversationSessionManager,
    get_session_registry
)

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL", "")
# Try SUPABASE_SERVICE_KEY first (standard naming), fallback to SUPABASE_KEY
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")

if not supabase_url or not supabase_key:
    st.error("⚠️ Supabase credentials not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file")
    st.info("💡 To set up Supabase, please refer to the QUICKSTART.md guide")
    st.stop()

supabase_client: Client = create_client(supabase_url, supabase_key)

# Page configuration
st.set_page_config(
    page_title="CASCADE",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
.stButton>button {
    width: 100%;
}
.feedback-button {
    margin: 5px;
}
</style>
""", unsafe_allow_html=True)


# Authentication functions

def sign_up(email: str, password: str, full_name: str):
    """Register new user."""
    try:
        response = supabase_client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name
                }
            }
        })
        if response and response.user:
            st.session_state.authenticated = True
            st.session_state.user = response.user
            st.rerun()
        return response
    except Exception as e:
        st.error(f"❌ Error signing up: {str(e)}")
        return None


def sign_in(email: str, password: str):
    """Sign in existing user."""
    try:
        response = supabase_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if response and response.user:
            st.session_state.authenticated = True
            st.session_state.user = response.user
            st.rerun()
        return response
    except Exception as e:
        st.error(f"❌ Error signing in: {str(e)}")
        return None


def sign_out():
    """Sign out current user."""
    try:
        supabase_client.auth.sign_out()
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.logout_requested = True
    except Exception as e:
        st.error(f"❌ Error signing out: {str(e)}")


# Initialize session state

if "messages" not in st.session_state:
    st.session_state.messages = []

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user" not in st.session_state:
    st.session_state.user = None

if "conversation_session" not in st.session_state:
    st.session_state.conversation_session = None

if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = None

if "waiting_for_feedback" not in st.session_state:
    st.session_state.waiting_for_feedback = False

if "current_solution" not in st.session_state:
    st.session_state.current_solution = None

if "improvement_mode" not in st.session_state:
    st.session_state.improvement_mode = False

if "continue_mode" not in st.session_state:
    st.session_state.continue_mode = False

# Check for logout flag
if st.session_state.get("logout_requested", False):
    st.session_state.logout_requested = False
    st.rerun()


# Async function to initialize orchestrator

async def initialize_orchestrator():
    """Initialize Orchestrator with DeepSolver tool."""
    if st.session_state.orchestrator is None:
        orchestrator = await create_orchestrator(deep_solver_tool=solve_with_deep_solver)
        st.session_state.orchestrator = orchestrator
        return orchestrator
    return st.session_state.orchestrator


# Main app

def main():
    """Main application entry point."""

    # Sidebar for authentication and settings
    with st.sidebar:
        st.title("🧪 CASCADE")

        if not st.session_state.authenticated:
            # Login/Signup tabs
            tab1, tab2 = st.tabs(["Login", "Sign Up"])

            with tab1:
                st.subheader("Login")
                login_email = st.text_input("Email", key="login_email")
                login_password = st.text_input("Password", type="password", key="login_password")
                login_button = st.button("Login", key="login_btn")

                if login_button:
                    if login_email and login_password:
                        sign_in(login_email, login_password)
                    else:
                        st.warning("⚠️ Please enter both email and password")

            with tab2:
                st.subheader("Sign Up")
                signup_email = st.text_input("Email", key="signup_email")
                signup_password = st.text_input("Password", type="password", key="signup_password")
                signup_name = st.text_input("Full Name", key="signup_name")
                signup_button = st.button("Sign Up", key="signup_btn")

                if signup_button:
                    if signup_email and signup_password and signup_name:
                        response = sign_up(signup_email, signup_password, signup_name)
                        if response and response.user:
                            st.success("✅ Sign up successful! Please check your email to confirm.")
                    else:
                        st.warning("⚠️ Please fill in all fields")

        else:
            # User is authenticated
            user = st.session_state.user
            st.success(f"👤 Logged in as: {user.email}")
            st.button("Logout", on_click=sign_out, key="logout_btn")

            st.divider()

            # =====================================================
            # Saved Conversations Section
            # =====================================================
            st.subheader("⭐ Saved Conversations")

            # Get database path
            if st.session_state.conversation_session:
                db_path = st.session_state.conversation_session.db_path
            else:
                db_path = CONVERSATIONS_DB_PATH

            # List saved sessions
            try:
                saved_sessions = ConversationSessionManager.list_saved_sessions(user.id, db_path=db_path)

                if saved_sessions:
                    # Use expander for saved conversations
                    with st.expander(f"📌 {len(saved_sessions)} Saved", expanded=True):
                        for session_data in saved_sessions:
                            session_id = session_data["session_id"]
                            custom_title = session_data["custom_title"]
                            notes = session_data["notes"]

                            # Get preview if no custom title
                            if custom_title:
                                display_title = custom_title
                            else:
                                try:
                                    preview_result = ConversationSessionManager.get_session_preview(session_id, db_path=db_path)
                                    if preview_result and len(preview_result) == 2:
                                        display_title, msg_count = preview_result
                                    else:
                                        display_title = "Saved Session"
                                except:
                                    display_title = "Saved Session"

                            # Current session indicator
                            is_current = bool(
                                st.session_state.conversation_session and
                                st.session_state.conversation_session.session_id == session_id
                            )

                            # Create columns for session button and unsave button
                            col1, col2 = st.columns([4, 1])

                            with col1:
                                button_label = f"{'🟢' if is_current else '⭐'} {display_title[:40]}"
                                if st.button(
                                    button_label,
                                    key=f"load_saved_{session_id}",
                                    disabled=is_current,
                                    use_container_width=True
                                ):
                                    # Load session
                                    st.session_state.conversation_session = ConversationSessionManager(
                                        session_id=session_id,
                                        user_id=user.id,
                                        db_path=db_path,
                                        load_existing=True
                                    )

                                    # Load messages
                                    loaded_messages = ConversationSessionManager.load_session_messages(session_id, db_path=db_path)
                                    st.session_state.messages = loaded_messages

                                    # Reset feedback states
                                    st.session_state.waiting_for_feedback = False
                                    st.session_state.current_solution = None
                                    st.session_state.improvement_mode = False
                                    st.session_state.continue_mode = False

                                    st.success("✅ Loaded saved conversation")
                                    st.rerun()

                            with col2:
                                # Unsave button
                                if st.button("☆", key=f"unsave_{session_id}", help="Remove from saved"):
                                    ConversationSessionManager.toggle_saved_status(session_id, False, db_path)
                                    st.success("Removed from saved")
                                    st.rerun()

                            # Show notes if present
                            if notes:
                                st.caption(f"📝 {notes[:50]}{'...' if len(notes) > 50 else ''}")

                else:
                    st.info("No saved conversations yet")

            except Exception as e:
                st.error(f"❌ Error loading saved sessions: {e}")

            st.divider()

            # Conversation History section
            st.subheader("📚 Conversation History")

            # New Conversation button
            if st.button("➕ New Conversation", key="new_conv_btn", use_container_width=True):
                # Create new session with timestamp
                new_session_id = f"session_{user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                db_path = CONVERSATIONS_DB_PATH
                st.session_state.conversation_session = ConversationSessionManager(
                    session_id=new_session_id,
                    user_id=user.id,
                    db_path=db_path,
                    load_existing=False
                )
                # Clear messages for new conversation
                st.session_state.messages = []
                st.session_state.waiting_for_feedback = False
                st.session_state.current_solution = None
                st.session_state.improvement_mode = False
                st.session_state.continue_mode = False
                st.success("✅ New conversation started!")
                st.rerun()

            # List previous sessions
            try:
                # Get database path from existing session or use default
                if st.session_state.conversation_session:
                    db_path = st.session_state.conversation_session.db_path
                else:
                    # Use parent directory for database (since we're in frontend/)
                    db_path = CONVERSATIONS_DB_PATH

                sessions = ConversationSessionManager.list_user_sessions(user.id, db_path=db_path, limit=20)

                if sessions:
                    # Group sessions by date
                    from datetime import datetime as dt, timedelta
                    now = dt.now()
                    today = now.date()
                    yesterday = today - timedelta(days=1)
                    week_ago = today - timedelta(days=7)

                    grouped_sessions = {
                        "Today": [],
                        "Yesterday": [],
                        "This Week": [],
                        "Older": []
                    }

                    for session_id, created_at, updated_at in sessions:
                        # Parse updated_at timestamp (format: YYYY-MM-DD HH:MM:SS)
                        try:
                            # Handle both string and None types
                            if updated_at:
                                session_date = dt.strptime(updated_at.split('.')[0], '%Y-%m-%d %H:%M:%S').date()
                            else:
                                session_date = today
                        except Exception as parse_error:
                            session_date = today  # Fallback to today if parse fails

                        if session_date == today:
                            grouped_sessions["Today"].append((session_id, created_at, updated_at))
                        elif session_date == yesterday:
                            grouped_sessions["Yesterday"].append((session_id, created_at, updated_at))
                        elif session_date > week_ago:
                            grouped_sessions["This Week"].append((session_id, created_at, updated_at))
                        else:
                            grouped_sessions["Older"].append((session_id, created_at, updated_at))

                    # Display grouped sessions
                    for group_name, group_sessions in grouped_sessions.items():
                        if group_sessions:
                            st.write(f"**{group_name}**")

                            for session_id, created_at, updated_at in group_sessions:
                                # Get preview
                                try:
                                    preview_result = ConversationSessionManager.get_session_preview(session_id, db_path=db_path)
                                    if preview_result and len(preview_result) == 2:
                                        preview_text, msg_count = preview_result
                                    else:
                                        preview_text = "Unknown session"
                                        msg_count = 0
                                except Exception as preview_error:
                                    preview_text = "Error loading preview"
                                    msg_count = 0

                                # Get saved status
                                try:
                                    metadata = ConversationSessionManager.get_session_metadata(session_id, db_path=db_path)
                                    is_saved = metadata["is_saved"] if metadata else False
                                except:
                                    is_saved = False

                                # Current session indicator
                                is_current = bool(
                                    st.session_state.conversation_session and
                                    st.session_state.conversation_session.session_id == session_id
                                )

                                # Create columns for session button and star button
                                col1, col2 = st.columns([4, 1])

                                with col1:
                                    # Create button label
                                    if is_current:
                                        button_label = f"🟢 {preview_text} ({msg_count} msgs)"
                                    else:
                                        button_label = f"💬 {preview_text} ({msg_count} msgs)"

                                    # Session button
                                    if st.button(
                                        button_label,
                                        key=f"load_{session_id}",
                                        disabled=is_current,
                                        use_container_width=True
                                    ):
                                        # Load session
                                        st.session_state.conversation_session = ConversationSessionManager(
                                            session_id=session_id,
                                            user_id=user.id,
                                            db_path=db_path,
                                            load_existing=True
                                        )

                                        # Load messages
                                        loaded_messages = ConversationSessionManager.load_session_messages(session_id, db_path=db_path)
                                        st.session_state.messages = loaded_messages

                                        # Reset feedback states
                                        st.session_state.waiting_for_feedback = False
                                        st.session_state.current_solution = None
                                        st.session_state.improvement_mode = False
                                        st.session_state.continue_mode = False

                                        st.success(f"✅ Loaded session with {msg_count} messages")
                                        st.rerun()

                                with col2:
                                    # Star/unstar button
                                    star_icon = "⭐" if is_saved else "☆"
                                    star_help = "Remove from saved" if is_saved else "Save conversation"
                                    if st.button(star_icon, key=f"star_{session_id}", help=star_help):
                                        ConversationSessionManager.toggle_saved_status(session_id, not is_saved, db_path)
                                        st.success(f"{'Saved' if not is_saved else 'Unsaved'} conversation")
                                        st.rerun()
                else:
                    st.info("No previous conversations yet")

            except Exception as e:
                st.error(f"❌ Error loading sessions: {e}")

            st.divider()

            # Session info
            st.subheader("📊 Session Info")
            if st.session_state.conversation_session:
                session_info = st.session_state.conversation_session.get_session_info()
                st.caption(f"Session ID: {session_info['session_id'][:8]}...")
                st.caption(f"Idle time: {int(session_info['idle_time'])}s")

                # Export conversation history
                st.write("**📥 Export Chat History**")

                if st.button("Export Conversation", key="export_md"):
                    try:
                        # Call async method using asyncio.run()
                        markdown_content = asyncio.run(
                            st.session_state.conversation_session.export_conversation_history()
                        )

                        # Create download button
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"conversation_{timestamp}.md"

                        st.download_button(
                            label="📥 Download Markdown",
                            data=markdown_content,
                            file_name=filename,
                            mime="text/markdown",
                            key="download_md"
                        )
                        st.success("✅ Ready to download!")
                    except Exception as e:
                        st.error(f"❌ Export error: {e}")

                st.divider()

                # Save Conversation section
                st.write("**💾 Save This Conversation**")

                # Get current session metadata
                current_session_id = st.session_state.conversation_session.session_id
                try:
                    metadata = ConversationSessionManager.get_session_metadata(current_session_id, db_path)
                    is_saved = metadata["is_saved"] if metadata else False
                    current_title = metadata["custom_title"] if metadata and metadata["custom_title"] else ""
                    current_notes = metadata["notes"] if metadata and metadata["notes"] else ""
                except:
                    is_saved = False
                    current_title = ""
                    current_notes = ""

                if is_saved:
                    st.info("⭐ This conversation is saved")
                    # Show edit form
                    with st.expander("✏️ Edit Title & Notes", expanded=False):
                        edit_title = st.text_input("Title", value=current_title, key="edit_title", placeholder="Enter a title (optional)")
                        edit_notes = st.text_area("Notes", value=current_notes, key="edit_notes", placeholder="Add notes about this conversation")

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Update", key="update_metadata", use_container_width=True):
                                # Always pass the values (including empty strings) to allow clearing
                                ConversationSessionManager.set_session_metadata(
                                    current_session_id,
                                    custom_title=edit_title.strip() if edit_title else "",
                                    notes=edit_notes.strip() if edit_notes else "",
                                    db_path=db_path
                                )
                                st.success("✅ Updated!")
                                st.rerun()

                        with col2:
                            if st.button("Remove from Saved", key="remove_saved", use_container_width=True):
                                ConversationSessionManager.toggle_saved_status(current_session_id, False, db_path)
                                st.success("Removed from saved")
                                st.rerun()
                else:
                    # Show save form
                    with st.expander("💾 Save with Title & Notes", expanded=False):
                        save_title = st.text_input("Title", key="save_title", placeholder="Enter a title (optional)")
                        save_notes = st.text_area("Notes", key="save_notes", placeholder="Add notes about this conversation")

                        if st.button("Save Conversation", key="save_conv", use_container_width=True):
                            # Set metadata first (if provided)
                            if save_title or save_notes:
                                ConversationSessionManager.set_session_metadata(
                                    current_session_id,
                                    custom_title=save_title if save_title else None,
                                    notes=save_notes if save_notes else None,
                                    db_path=db_path
                                )
                            # Mark as saved
                            ConversationSessionManager.toggle_saved_status(current_session_id, True, db_path)
                            st.success("✅ Conversation saved!")
                            st.rerun()

                st.divider()

                if st.button("Clear Conversation History"):
                    st.session_state.conversation_session.clear_session()
                    st.session_state.messages = []
                    st.success("🗑️ History cleared")
                    st.rerun()

    # Main conversation area
    if st.session_state.authenticated and st.session_state.user:
        user_id = st.session_state.user.id

        # Initialize conversation session if needed
        if st.session_state.conversation_session is None:
            session_id = f"session_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            db_path = CONVERSATIONS_DB_PATH
            st.session_state.conversation_session = ConversationSessionManager(
                session_id=session_id,
                user_id=user_id,
                db_path=db_path
            )

        # Optional: Check for very long inactivity (30 minutes) to prevent memory leaks
        # This only clears the feedback state, NOT the conversation history
        if st.session_state.conversation_session.is_timeout(timeout_seconds=1800):  # 30 minutes
            if st.session_state.waiting_for_feedback:
                st.info("ℹ️ Feedback timeout - you can continue the conversation or start a new question.")
                # Only clear feedback state, keep conversation history
                st.session_state.waiting_for_feedback = False
                st.session_state.current_solution = None
                st.session_state.improvement_mode = False

        st.title("💬 Conversational Assistant")
        st.write("Ask me anything about computational materials science and chemistry!")

        # Display conversation history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

                # Show code if present
                if "code" in msg and msg["code"]:
                    with st.expander("📝 View Code"):
                        st.code(msg["code"], language="python")

                # Show execution results if present
                if "results" in msg and msg["results"]:
                    with st.expander("📊 Execution Results"):
                        st.text(msg["results"])

        # Feedback buttons (if waiting for feedback)
        if st.session_state.waiting_for_feedback:
            st.divider()
            st.write("**How would you like to proceed?**")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("✅ Save Solution", type="primary", key="save_btn"):
                    # Send satisfaction message to Orchestrator to trigger save_to_memory
                    # Include original query for context
                    original_q = st.session_state.conversation_session.get_original_query()
                    if original_q:
                        satisfaction_message = f"[ORIGINAL_QUERY: {original_q}]\nI'm satisfied with the solution. Please save it to memory for future reference."
                        display_message = "I'm satisfied with the solution. Please save it to memory for future reference."
                    else:
                        satisfaction_message = "I'm satisfied with the solution. Please save it to memory for future reference."
                        display_message = satisfaction_message

                    # Add to message history (display version without ORIGINAL_QUERY tag)
                    st.session_state.messages.append({
                        "role": "user",
                        "content": display_message
                    })

                    # Display user message
                    with st.chat_message("user"):
                        st.write(display_message)

                    # Clear feedback state
                    st.session_state.waiting_for_feedback = False
                    st.session_state.current_solution = None

                    # Run orchestrator to save the solution
                    with st.spinner("💾 Saving solution to memory..."):
                        try:
                            # Initialize orchestrator if needed
                            orchestrator = asyncio.run(initialize_orchestrator())

                            # Run conversation turn (use satisfaction_message with ORIGINAL_QUERY tag)
                            result = asyncio.run(
                                st.session_state.conversation_session.run_conversation_turn(
                                    orchestrator,
                                    satisfaction_message  # This includes [ORIGINAL_QUERY: xxx] if available
                                )
                            )

                            # Get response
                            response_text = str(result.final_output) if hasattr(result, 'final_output') else str(result)

                            # Add assistant response to history
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response_text
                            })

                            # Display success message
                            with st.chat_message("assistant"):
                                st.write(response_text)

                            # Reset for new query
                            st.session_state.conversation_session.reset_for_new_query()

                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")

                    st.rerun()

            with col2:
                if st.button("🔧 Request Improvements", key="improve_btn"):
                    st.session_state.improvement_mode = True
                    # Keep waiting_for_feedback=True to preserve original_query tracking
                    # (we're still in the same problem-solving session)
                    st.rerun()

            with col3:
                if st.button("➕ Continue", key="continue_btn"):
                    st.session_state.continue_mode = True
                    # Keep waiting_for_feedback=True
                    st.rerun()

            with col4:
                if st.button("❌ Exit", key="exit_btn"):
                    # Send exit message to Orchestrator
                    exit_message = "I don't want to save this solution. Let's move on."

                    # Add to message history
                    st.session_state.messages.append({
                        "role": "user",
                        "content": exit_message
                    })

                    # Display user message
                    with st.chat_message("user"):
                        st.write(exit_message)

                    # Clear feedback state but keep conversation history
                    st.session_state.waiting_for_feedback = False
                    st.session_state.current_solution = None

                    # Run orchestrator to acknowledge exit
                    with st.spinner("Processing..."):
                        try:
                            # Initialize orchestrator if needed
                            orchestrator = asyncio.run(initialize_orchestrator())

                            # Run conversation turn
                            result = asyncio.run(
                                st.session_state.conversation_session.run_conversation_turn(
                                    orchestrator,
                                    exit_message
                                )
                            )

                            # Get response
                            response_text = str(result.final_output) if hasattr(result, 'final_output') else str(result)

                            # Add assistant response to history
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response_text
                            })

                            # Display response
                            with st.chat_message("assistant"):
                                st.write(response_text)

                            # Reset for new query (clears original_query for next problem)
                            st.session_state.conversation_session.reset_for_new_query()

                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")

                    st.rerun()

        # Improvement request input
        if st.session_state.improvement_mode:
            st.divider()
            st.subheader("🔧 Request Improvements")

            improvement_text = st.text_area(
                "What would you like to improve?",
                placeholder="Describe what you'd like to change or improve...",
                key="improvement_text"
            )

            if st.button("Submit Improvement Request", key="submit_improvement"):
                if improvement_text:
                    # Format as improvement request, include original query for context
                    original_q = st.session_state.conversation_session.get_original_query()
                    if original_q:
                        user_input = f"[ORIGINAL_QUERY: {original_q}]\n🔧 Improvement request: {improvement_text}"
                    else:
                        user_input = f"🔧 Improvement request: {improvement_text}"

                    # Add user message to history (without the ORIGINAL_QUERY tag for display)
                    display_message = f"🔧 Improvement request: {improvement_text}"
                    st.session_state.messages.append({
                        "role": "user",
                        "content": display_message
                    })

                    # Display user message
                    with st.chat_message("user"):
                        st.write(display_message)

                    st.session_state.improvement_mode = False

                    # Run orchestrator to process the improvement request
                    with st.spinner("🤔 Processing improvement request..."):
                        try:
                            # Initialize orchestrator if needed
                            orchestrator = asyncio.run(initialize_orchestrator())

                            # Run conversation turn
                            result = asyncio.run(
                                st.session_state.conversation_session.run_conversation_turn(
                                    orchestrator,
                                    user_input
                                )
                            )

                            # Process result
                            assistant_response = result.final_output

                            # Handle None or empty response first
                            if assistant_response is None:
                                response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                code = ""
                                results = ""
                                st.session_state.waiting_for_feedback = False

                            # Extract components if structured
                            elif isinstance(assistant_response, dict):
                                response_text = assistant_response.get("explanation", "")
                                code = assistant_response.get("final_code", "")
                                results = assistant_response.get("execution_results", "")
                                success = assistant_response.get("success", False)

                                # Check if response is empty
                                if not response_text or not response_text.strip():
                                    response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                    st.session_state.waiting_for_feedback = False
                                # Store current solution if successful
                                elif success and code:
                                    st.session_state.current_solution = {
                                        "query": user_input,
                                        "code": code,
                                        "explanation": response_text,
                                        "results": results,
                                        "metadata": {}
                                    }
                                    st.session_state.waiting_for_feedback = True

                            else:
                                # Free-form text response (from Orchestrator)
                                response_text = str(assistant_response) if assistant_response else ""
                                code = ""
                                results = ""

                                # Check if response is empty first
                                if not response_text or not response_text.strip() or response_text == "None":
                                    response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                    st.session_state.waiting_for_feedback = False
                                else:
                                    # Only show feedback buttons if this looks like a final answer
                                    # Don't show if orchestrator is asking a question or confirming
                                    is_question = response_text.strip().endswith('?')
                                    is_short_response = len(response_text.strip()) < 100
                                    looks_like_final_answer = not is_question and not is_short_response

                                    if looks_like_final_answer:
                                        st.session_state.current_solution = {
                                            "query": user_input,
                                            "code": "",
                                            "explanation": response_text,
                                            "results": "",
                                            "metadata": {}
                                        }
                                        st.session_state.waiting_for_feedback = True
                                    # else: Don't set waiting_for_feedback - let user respond to question

                            # Add assistant message to history
                            msg_data = {
                                "role": "assistant",
                                "content": response_text
                            }
                            if code:
                                msg_data["code"] = code
                            if results:
                                msg_data["results"] = results

                            st.session_state.messages.append(msg_data)

                            # Display assistant response
                            with st.chat_message("assistant"):
                                st.write(response_text)

                                if code:
                                    with st.expander("📝 View Code"):
                                        st.code(code, language="python")

                                if results:
                                    with st.expander("📊 Execution Results"):
                                        st.text(results)

                            st.rerun()

                        except Exception as e:
                            error_msg = f"I apologize, but I encountered an error: {str(e)}"
                            st.error(f"❌ Error: {str(e)}")

                            # Add and display error message
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": error_msg
                            })

                            with st.chat_message("assistant"):
                                st.write(error_msg)

                            # Don't show feedback buttons after error
                            st.session_state.waiting_for_feedback = False
                            st.rerun()
                else:
                    st.warning("⚠️ Please describe what you'd like to improve")

        # Continue conversation
        if st.session_state.continue_mode:
            st.divider()
            st.subheader("➕ Continue Conversation")
            st.info("💡 Add more details, ask follow-up questions, or provide additional context to continue the conversation.")

            continue_text = st.text_area(
                "What would you like to add or ask?",
                placeholder="Add more details, ask follow-up questions, provide constraints, or clarify your needs...",
                key="continue_text"
            )

            if st.button("Submit", key="submit_continue"):
                if continue_text:
                    # Append to original query
                    st.session_state.conversation_session.append_to_original_query(continue_text)

                    # Format message with ORIGINAL_QUERY tag
                    original_q = st.session_state.conversation_session.get_original_query()
                    if original_q:
                        user_input = f"[ORIGINAL_QUERY: {original_q}]\n➕ Continue: {continue_text}"
                    else:
                        user_input = f"➕ Continue: {continue_text}"

                    # Add user message to history (without the ORIGINAL_QUERY tag for display)
                    display_message = f"➕ Continue: {continue_text}"
                    st.session_state.messages.append({
                        "role": "user",
                        "content": display_message
                    })

                    # Display user message
                    with st.chat_message("user"):
                        st.write(display_message)

                    st.session_state.continue_mode = False

                    # Run orchestrator to process with updated query
                    with st.spinner("🤔 Processing with additional context..."):
                        try:
                            # Initialize orchestrator if needed
                            orchestrator = asyncio.run(initialize_orchestrator())

                            # Run conversation turn
                            result = asyncio.run(
                                st.session_state.conversation_session.run_conversation_turn(
                                    orchestrator,
                                    user_input
                                )
                            )

                            # Process result
                            assistant_response = result.final_output

                            # Handle None or empty response first
                            if assistant_response is None:
                                response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                code = ""
                                results = ""
                                st.session_state.waiting_for_feedback = False

                            # Extract components if structured
                            elif isinstance(assistant_response, dict):
                                response_text = assistant_response.get("explanation", "")
                                code = assistant_response.get("final_code", "")
                                results = assistant_response.get("execution_results", "")
                                success = assistant_response.get("success", False)

                                # Check if response is empty
                                if not response_text or not response_text.strip():
                                    response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                    st.session_state.waiting_for_feedback = False
                                # Store current solution if successful
                                elif success and code:
                                    st.session_state.current_solution = {
                                        "query": continue_text,
                                        "code": code,
                                        "explanation": response_text,
                                        "results": results,
                                        "metadata": {}
                                    }
                                    st.session_state.waiting_for_feedback = True

                            else:
                                # Free-form text response (from Orchestrator)
                                response_text = str(assistant_response) if assistant_response else ""
                                code = ""
                                results = ""

                                # Check if response is empty first
                                if not response_text or not response_text.strip() or response_text == "None":
                                    response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                                    st.session_state.waiting_for_feedback = False
                                else:
                                    # Only show feedback buttons if this looks like a final answer
                                    # Don't show if orchestrator is asking a question or confirming
                                    is_question = response_text.strip().endswith('?')
                                    is_short_response = len(response_text.strip()) < 100
                                    looks_like_final_answer = not is_question and not is_short_response

                                    if looks_like_final_answer:
                                        st.session_state.current_solution = {
                                            "query": continue_text,
                                            "code": "",
                                            "explanation": response_text,
                                            "results": "",
                                            "metadata": {}
                                        }
                                        st.session_state.waiting_for_feedback = True
                                    # else: Don't set waiting_for_feedback - let user respond to question

                            # Add assistant message to history
                            msg_data = {
                                "role": "assistant",
                                "content": response_text
                            }
                            if code:
                                msg_data["code"] = code
                            if results:
                                msg_data["results"] = results

                            st.session_state.messages.append(msg_data)

                            # Display assistant message
                            with st.chat_message("assistant"):
                                st.write(response_text)

                                if code:
                                    with st.expander("📝 View Code"):
                                        st.code(code, language="python")

                                if results:
                                    with st.expander("📊 Execution Results"):
                                        st.text(results)

                            st.rerun()

                        except Exception as e:
                            error_msg = f"I apologize, but I encountered an error: {str(e)}"
                            st.error(f"❌ Error: {str(e)}")

                            # Add and display error message
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": error_msg
                            })

                            with st.chat_message("assistant"):
                                st.write(error_msg)

                            # Don't show feedback buttons after error
                            st.session_state.waiting_for_feedback = False
                            st.rerun()
                else:
                    st.warning("⚠️ Please enter your message")

        # User input (disabled when waiting for feedback to encourage using the 4 buttons)
        user_input = st.chat_input(
            "Type your question here..." if not st.session_state.waiting_for_feedback
            else "Please use the buttons above to proceed...",
            disabled=st.session_state.waiting_for_feedback
        )

        if user_input:
            # Set original query if this is the first message in current problem-solving session
            if not st.session_state.waiting_for_feedback:
                st.session_state.conversation_session.set_original_query(user_input)

            # Add user message to history
            st.session_state.messages.append({
                "role": "user",
                "content": user_input
            })

            # Display user message
            with st.chat_message("user"):
                st.write(user_input)

            # Run orchestrator (async)
            with st.spinner("🤔 Thinking..."):
                try:
                    # Initialize orchestrator if needed
                    orchestrator = asyncio.run(initialize_orchestrator())

                    # Run conversation turn
                    result = asyncio.run(
                        st.session_state.conversation_session.run_conversation_turn(
                            orchestrator,
                            user_input
                        )
                    )

                    # Process result
                    assistant_response = result.final_output

                    # Handle None or empty response first
                    if assistant_response is None:
                        response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                        code = ""
                        results = ""
                        st.session_state.waiting_for_feedback = False

                    # Extract components if structured
                    elif isinstance(assistant_response, dict):
                        response_text = assistant_response.get("explanation", "")
                        code = assistant_response.get("final_code", "")
                        results = assistant_response.get("execution_results", "")
                        success = assistant_response.get("success", False)

                        # Check if response is empty
                        if not response_text or not response_text.strip():
                            response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                            st.session_state.waiting_for_feedback = False
                        # Store current solution if successful
                        elif success and code:
                            st.session_state.current_solution = {
                                "query": user_input,
                                "code": code,
                                "explanation": response_text,
                                "results": results,
                                "metadata": {}
                            }
                            st.session_state.waiting_for_feedback = True

                    else:
                        # Free-form text response (from Orchestrator)
                        response_text = str(assistant_response) if assistant_response else ""
                        code = ""
                        results = ""

                        # Check if response is empty first
                        if not response_text or not response_text.strip() or response_text == "None":
                            response_text = "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
                            st.session_state.waiting_for_feedback = False
                        else:
                            # Only show feedback buttons if this looks like a final answer
                            # Don't show if orchestrator is asking a question or confirming
                            is_question = response_text.strip().endswith('?')
                            is_short_response = len(response_text.strip()) < 100
                            looks_like_final_answer = not is_question and not is_short_response

                            if looks_like_final_answer:
                                st.session_state.current_solution = {
                                    "query": user_input,
                                    "code": "",
                                    "explanation": response_text,
                                    "results": "",
                                    "metadata": {}
                                }
                                st.session_state.waiting_for_feedback = True
                            # else: Don't set waiting_for_feedback - let user respond to question

                    # Add assistant message to history
                    msg_data = {
                        "role": "assistant",
                        "content": response_text
                    }
                    if code:
                        msg_data["code"] = code
                    if results:
                        msg_data["results"] = results

                    st.session_state.messages.append(msg_data)

                    # Display assistant response
                    with st.chat_message("assistant"):
                        st.write(response_text)

                        if code:
                            with st.expander("📝 View Code"):
                                st.code(code, language="python")

                        if results:
                            with st.expander("📊 Execution Results"):
                                st.text(results)

                    st.rerun()

                except Exception as e:
                    error_msg = f"I apologize, but I encountered an error: {str(e)}"
                    st.error(f"❌ Error: {str(e)}")

                    # Add and display error message
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })

                    with st.chat_message("assistant"):
                        st.write(error_msg)

                    # Don't show feedback buttons after error
                    st.session_state.waiting_for_feedback = False
                    st.rerun()

    else:
        # Welcome screen for unauthenticated users
        st.title("🧪 Welcome to CASCADE")
        st.write("Please login or sign up to start chatting with the AI assistant for materials science and chemistry.")

        st.divider()

        st.subheader("✨ Features")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("### 🧠 Memory-Powered")
            st.write("Remembers your preferences and past successful solutions")

        with col2:
            st.markdown("### 🔬 Deep Research")
            st.write("Comprehensive research and debugging for complex problems")

        with col3:
            st.markdown("### 💬 Multi-Turn")
            st.write("Natural conversation with feedback and improvements")


if __name__ == "__main__":
    main()
