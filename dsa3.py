import streamlit as st
from collections import deque
from datetime import datetime
import time
import random
import json
import os
from pathlib import Path


QUEUE_FILE = Path("shared_queue_data.json")


class QueueManager:
    def __init__(self):
        self.message_queue = []
        self.processing_queue = []
        self.response_queue = []
        self.conversation_history = []
        self.active_users = {}
        self.start_time = datetime.now().isoformat()
        self.queue_log = []
        self.last_process_time = None
        self.total_messages = 0
        self.processed_count = 0

    def to_dict(self):
        return {
            'message_queue': self.message_queue,
            'processing_queue': self.processing_queue,
            'response_queue': self.response_queue,
            'conversation_history': self.conversation_history[-100:],
            'total_messages': self.total_messages,
            'processed_count': self.processed_count,
            'active_users': self.active_users,
            'start_time': self.start_time,
            'queue_log': self.queue_log[-50:],
            'last_process_time': self.last_process_time
        }

    @staticmethod
    def from_dict(data):
        qm = QueueManager()
        qm.message_queue = data.get('message_queue', [])
        qm.processing_queue = data.get('processing_queue', [])
        qm.response_queue = data.get('response_queue', [])
        qm.conversation_history = data.get('conversation_history', [])
        qm.total_messages = data.get('total_messages', 0)
        qm.processed_count = data.get('processed_count', 0)
        qm.active_users = data.get('active_users', {})
        qm.start_time = data.get('start_time', datetime.now().isoformat())
        qm.queue_log = data.get('queue_log', [])
        qm.last_process_time = data.get('last_process_time')
        return qm

    def enqueue(self, msg_obj):
        self.message_queue.append(msg_obj)

    def dequeue(self):
        if self.message_queue:
            return self.message_queue.pop(0)
        return None

    def add_user_message(self, message, user_id):
        msg_obj = {
            'id': self.total_messages + 1,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
        }
        self.enqueue(msg_obj)
        self.total_messages += 1
        self.active_users[user_id] = datetime.now().isoformat()
        self.queue_log.append({
            'time': datetime.now().isoformat(),
            'action': 'enqueued',
            'queue_size': len(self.message_queue)
        })

    def process_next_message(self, knowledge_base):
        current_time = time.time()
        if self.last_process_time and (current_time - self.last_process_time) < 3.0:
            return False

        msg = self.dequeue()
        if msg:
            self.processing_queue.append(msg)
            self.last_process_time = current_time

            procedure = knowledge_base.search_procedure(msg['message'])
            if procedure:
                response_text = procedure['response']
            else:
                response_text = knowledge_base.get_default_help()

            response = {
                'id': msg['id'],
                'response': response_text,
                'original_message': msg['message'],
                'user_id': msg['user_id'],
                'timestamp': datetime.now().isoformat(),
            }
            self.response_queue.append(response)

            if self.processing_queue:
                self.processing_queue.pop(0)
            self.processed_count += 1
            return True
        return False

    def get_queue_position(self, user_id):
        for idx, msg in enumerate(self.message_queue):
            if msg['user_id'] == user_id:
                return idx + 1
        return 0

    def clean_inactive_users(self, timeout_seconds=15):
        """Remove users who haven't been active for timeout_seconds"""
        current_time = datetime.now()
        inactive_users = []

        for user_id, last_active in list(self.active_users.items()):
            try:
                last_active_time = datetime.fromisoformat(last_active)
                if (current_time - last_active_time).total_seconds() > timeout_seconds:
                    inactive_users.append(user_id)
            except:
                inactive_users.append(user_id)

        for user_id in inactive_users:
            del self.active_users[user_id]

    def update_user_activity(self, user_id):
        """A simple method to update a user's last seen timestamp."""
        self.active_users[user_id] = datetime.now().isoformat()

    def get_queue_stats(self): 
        self.clean_inactive_users()

        try:
            start = datetime.fromisoformat(self.start_time)
            uptime = (datetime.now() - start).total_seconds()
        except:
            uptime = 0
        avg_time = uptime / self.processed_count if self.processed_count > 0 else 0
        return {
            'total_input': len(self.message_queue),
            'processing': len(self.processing_queue),
            'response_queue': len(self.response_queue),
            'total_processed': self.processed_count,
            'active_users': len(self.active_users),
            'avg_processing_time': avg_time,
            'uptime_seconds': int(uptime)
        }

    def get_response(self, user_id):
        for i, response in enumerate(self.response_queue):
            if response['user_id'] == user_id:
                self.response_queue.pop(i)
                self.conversation_history.append({
                    'user': response['original_message'],
                    'bot': response['response'],
                    'time': datetime.fromisoformat(response['timestamp']).strftime("%H:%M:%S"),
                    'user_id': user_id
                })
                return response
        return None


    def peek_next_message(self):
        if self.message_queue:
            return self.message_queue[0]
        return None

    def clear_all_queues(self):
        self.message_queue.clear()
        self.processing_queue.clear()
        self.response_queue.clear()



    def get_queue_health(self):
        stats = self.get_queue_stats()
        total_queue = stats['total_input']
        if total_queue == 0:
            return "🟢 Excellent", "No waiting requests"
        elif total_queue <= 3:
            return "🟡 Good", f"{total_queue} request(s) in queue"
        elif total_queue <= 7:
            return "🟠 Moderate", f"{total_queue} requests waiting"
        else:
            return "🔴 Heavy", f"{total_queue} requests - high traffic"

def save_queue(queue_manager):
    """Save queue to disk for sharing between sessions"""
    try:
        with open(QUEUE_FILE, 'w') as f:
            json.dump(queue_manager.to_dict(), f)
    except Exception as e:
        st.error(f"Error saving queue: {e}")


def load_queue():
    """Load shared queue from disk"""
    try:
        if QUEUE_FILE.exists():
            with open(QUEUE_FILE, 'r') as f:
                data = json.load(f)
                qm = QueueManager.from_dict(data)
                # Clean inactive users every time we load
                qm.clean_inactive_users(timeout_seconds=30)
                return qm
    except Exception as e:
        print(f"Error loading queue: {e}")
    return QueueManager()


class AIMSKnowledgeBase:
    def __init__(self):
        self.procedures = [
            {
                'keywords': ['enroll', 'enrollment', 'register', 'enlist', 'add subject'],
                'category': 'Enrollment',
                'response': """📄 **How to Enroll in Subjects via AIMS**

1.  **Log in** to your AIMS portal and navigate to the **Registration** tab.

2.  First, select your designated **Section** from the dropdown menu at the top right of the page (e.g., "A NORTH").

3.  In the **ADD SUBJECTS** section below, click the green circle next to each course you need to take for that section.

4.  For each added subject, use the "Schedule" dropdown to select a class time. The options will be based on the section you chose in step 2.

5.  After selecting all your schedules, scroll down and click the **Assess** button.

6.  This will take you to the final Registration (Assessment) page.

7.  To complete your enrollment, you must now pay your miscellaneous fees. Once payment is successful, the portal will confirm your status with the message: "YOU ARE NOW OFFICIALLY ENROLLED!"

💡 **Heads-Up:** For a smoother enrollment, it's a good idea to verify your official section with your department beforehand.
*If you encounter any problems please see the Registrars Office."""
            },
            {
                'keywords': ['pay tuition', 'tuition fee', 'how to pay', 'miscellaneous fee', 'make payment',
                             'payment process', 'assessment fee'],
                'category': 'Fee Payment',
                'response': """💳 **How to Pay Your Assessed Fees**

At UCC, tuition is free! The payment you make after enrolling is for your miscellaneous fees. Here's how to complete that process:

1.  On the final assessment page, locate the **TOTAL TUITION & FEES** section. This will show the total amount for your miscellaneous fees.

2.  Click on the **"Select mode of payment"** dropdown menu.

3.  Choose your preferred payment method from the list.

4.  After selecting a method, click the button to **Proceed with Payment**.

5.  Follow the instructions to complete the transaction for your miscellaneous fees.

6.  Once your payment is successful, always **save a copy of your transaction receipt** or Official Receipt (O.R.) for your records.

After your payment is confirmed, the page will update with the message, "**YOU ARE NOW OFFICIALLY ENROLLED!**"

💡 **Important:** Ensure you settle your miscellaneous fees before the payment deadline to validate your enrollment for the semester."""
            },
            {
                'keywords': ['grades', 'grade', 'gwa', 'marks', 'scores', 'results'],
                'category': 'Grades',
                'response': """📊 **How to Check Your Grades in AIMS**

1. Login to your AIMS portal account.

2. In the main navigation bar at the top, click on the "Grades" tab.

3. Select the appropriate School Year and Semester from the dropdown menus.

4. The page will display your grades table.

5. Review your grades for each subject listed.

📈 Understanding Your Grades:
* 1.0 – 3.0: Passing grades
* 4.0 – 5.0: Failing grades
* INC: Incomplete
* For inquiries, email: ucc@pinnacleasia.com"""
            },
            {
                'keywords': ['other payments', 'other fees'],
                'category': 'Other Payments',
                'response': """💸 **AIMS Other Payments Guide**

1. Login to your AIMS portal account.

2. Navigate to the **Other Payments** section on the portal.

3. Click on the **Other Fees** option from the menu.

4. Choose your academic **Section** from the list provided.

5. Select the specific fee you need to pay, then enter the required quantity and amount.

6. Click the **Continue to Payment** button to proceed and finalize the transaction.

💡 **Troubleshooting Tip:**
* If you encounter an error, please wait a few moments before trying the process again.
* For inquiries, email: ucc@pinnacleasia.com"""
            },
            {
                'keywords': ['schedule', 'class', 'timetable', 'time', 'room'],
                'category': 'Schedule',
                'response': """📅 **Checking Your Class Schedule**

1.  Login to your AIMS portal account.

2.  In the main navigation bar at the top, click on the **"Schedule"** tab.

3.  The page will display your complete class schedule for the current semester.

4.  You can easily find the specific time, day, and room assignment for each class in the timetable.

📱 **Pro Tip:** Take a screenshot of this page at the beginning of the semester so you always have an offline copy of your schedule."""
            },
            {
                'keywords': ['registration form', 'download registration', 'get registration form', 'cor', 'print form',
                             'enrollment form'],
                'category': 'Registration Form',
                'response': """📄 **How to Download Your Registration Form (COR)**

1.  **Log in** to your AIMS portal account.

2.  In the main navigation bar, click on the **Account** tab.

3.  On the Account page, click the **Registration Form** tab, which is located next to "Statement of Account".

4.  Your official Registration Form will now be displayed in a PDF viewer.

5.  To save or print your form, use the icons at the top of the PDF viewer:
    * Click the **Download** icon (downward arrow) to save a PDF copy directly to your computer.
    * Click the **Print** icon (printer symbol) to send the form to a printer.

💡 **Pro Tip:** Always save a digital copy of your registration form at the beginning of the semester for your records."""
            },
            {
                'keywords': ['statement of account', 'soa', 'payment history', 'account history', 'check balance',
                             'view balance', 'fees paid', 'payment records'],
                'category': 'Account History',
                'response': """📜 **How to Check Your Payment History (Statement of Account)**

1.  **Log in** to your AIMS portal account.

2.  In the main navigation bar, click on the **Account** tab.

3.  Under the **Assessment Fees** section, click on a specific semester to view its detailed breakdown.

4.  The page will display your full Statement of Account for that term.

5.  To download an official copy, click the **Statement of Account** link, usually found in the upper or lower left corner of the page.

**Understanding Your Statement:**
* **Assessment:** The total amount billed for your fees.
* **Payment:** The total amount you have already paid.
* **Balance:** The remaining amount you still need to settle.

📞 **For Inquiries:**
* If you have questions about your statement, please see the Registrar's Office."""
            },
            {
                'keywords': ['password', 'change password', 'update password', 'reset password', 'account security'],
                'category': 'Password',
                'response': """🔑 **How to Change Your AIMS Password**

Follow these steps to update your account password for better security.

1.  **Log in** to your AIMS portal account.

2.  Navigate to the **Password** tab in the main menu.

3.  In the **Old Password** field, enter your current password.

4.  In the **Choose a new password** and **Confirm Password** fields, enter your desired new password.

5.  Click the **Change Password** button to save your changes.

🔐 **Password Requirements:**
* If you see an error, make sure your new password meets the portal's security requirements (e.g., uppercase letters, numbers, symbols)."""
            }
        ]

    def search_procedure(self, user_message):
        user_msg_lower = user_message.lower()
        for procedure in self.procedures:
            if any(keyword in user_msg_lower for keyword in procedure['keywords']):
                return procedure
        return None

    def get_default_help(self):
        return """👋 **Welcome to AIMSsist!**

I'm your virtual assistant for the UCC AIMS Portal. I can help you with:

📄 **Enrollment** - How to register for subjects

💳 **Fee Payment** - How to pay your assessed miscellaneous fees

💸 **Other Payments** - Guides for other portal payments     
📊 **Grades** - How to check your semester grades

📅 **Schedule** - How to view your class schedule

🔑 **Password** - How to change your account password

📜 **Documents** - How to download your Registration Form and Statement Of Account

**Try asking:**
* "How do I enroll?"
* "How to pay my fees?"
* "How can I see my schedule?"

Type your question below! 👇"""

    def get_all_categories(self):
        categories = {}
        for proc in self.procedures:
            cat = proc['category']
            if cat not in categories:
                categories[cat] = proc['keywords'][0]
        return categories


def process_user_question(question, user_id):
    """Adds the user's question to the queue instantly."""
    if not question.strip():
        return
    queue_manager = load_queue()
    queue_manager.add_user_message(question, user_id)
    save_queue(queue_manager)


def main():
    st.set_page_config(
        page_title="AIMSsist - UCC",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    if 'knowledge_base' not in st.session_state:
        st.session_state.knowledge_base = AIMSKnowledgeBase()

    if not QUEUE_FILE.exists():
        initial_queue = QueueManager()
        save_queue(initial_queue)


    if 'user_id' not in st.session_state:
        st.session_state.user_id = f"Student_{random.randint(1000, 9999)}"

    if 'my_chat' not in st.session_state:
        st.session_state.my_chat = []
 
    queue_manager = load_queue()

    queue_manager.update_user_activity(st.session_state.user_id)
    save_queue(queue_manager)

    if queue_manager.message_queue:
        processed = queue_manager.process_next_message(st.session_state.knowledge_base)
        if processed:
            save_queue(queue_manager)

    # --- UI Code Starts Here ---
    col_header1, col_header2, col_header3 = st.columns([2, 1, 1])
    with col_header1:
        st.title("🎓 AIMSsist")
        st.markdown("**University of Caloocan City** | AIMS Portal Assistant")
    with col_header2:
        health_status, health_msg = queue_manager.get_queue_health()
        st.metric("System Status", health_status, health_msg)
    with col_header3:
        st.metric("Your ID", st.session_state.user_id[-4:])

    st.divider()

    col1, col2 = st.columns([2.5, 1])

    with col1:
        st.header("💬 Chat Assistant")
        chat_container = st.container(height=420)
        with chat_container:
            if st.session_state.my_chat:
                for entry in st.session_state.my_chat:
                    with st.chat_message("user", avatar="👤"):
                        st.write(entry['user'])
                        st.caption(f"⏰ {entry['time']}")
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(entry['bot'])
                        st.caption(f"⏰ {entry['time']}")
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(st.session_state.knowledge_base.get_default_help())

        # Check for responses
        queue_manager_reload = load_queue()  # Reload to get latest state
        response = queue_manager_reload.get_response(st.session_state.user_id)
        if response:
            st.session_state.my_chat.append({
                'user': response['original_message'],
                'bot': response['response'],
                'time': datetime.fromisoformat(response['timestamp']).strftime("%H:%M:%S"),
            })
            save_queue(queue_manager_reload)
            st.rerun()

        queue_pos = queue_manager.get_queue_position(st.session_state.user_id)
        if queue_pos > 0:
            st.warning(f"⏳ Your request is **#{queue_pos}** in the queue")

        stats = queue_manager.get_queue_stats()
        if stats['processing'] > 0:
            st.info("⚙️ Processing a request...")

        user_input = st.chat_input("Type your message here...")
        if user_input:
            process_user_question(user_input.strip(), st.session_state.user_id)
            st.rerun()

        col_clear, col_help = st.columns(2)
        with col_clear:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.my_chat.clear()
                st.rerun()
        with col_help:
            if st.button("❓ Help Menu", use_container_width=True):
                st.session_state.my_chat.append({
                    'user': 'Show help menu',
                    'bot': st.session_state.knowledge_base.get_default_help(),
                    'time': datetime.now().strftime("%H:%M:%S"),
                })
                st.rerun()

    with col2:
        st.header("📊 Queue Monitor")
        stats = queue_manager.get_queue_stats()
        st.markdown("##### 📥 Incoming Requests")
        st.progress(min(stats['total_input'] / 10, 1.0))
        st.caption(f"{stats['total_input']} requests in queue")
        st.divider()
        st.markdown("##### 📈 Statistics")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric("👥 Active Now", stats['active_users'], help="Users active in last 15 seconds")
        with col_s2:
            st.metric("📥 In Queue", stats['total_input'])
        st.divider()
        st.markdown("##### ⚡ Quick Questions")
        categories = st.session_state.knowledge_base.get_all_categories()
        for category, keyword in categories.items():
            if st.button(f"📌 {category}", use_container_width=True, key=f"cat_{category}"):
                process_user_question(keyword, st.session_state.user_id)
                st.rerun()

        st.divider()
        st.markdown("##### 📋 Current Queue")
        if queue_manager.message_queue:
            for idx, msg in enumerate(queue_manager.message_queue[:5], 1):
                user_short = msg['user_id'][-4:]
                msg_preview = msg['message'][:25] + "..." if len(msg['message']) > 25 else msg['message']
                st.caption(f"#{idx} - [{user_short}] {msg_preview}")
            if len(queue_manager.message_queue) > 5:
                st.caption(f"... and {len(queue_manager.message_queue) - 5} more")
        else:
            st.caption("Queue is empty")

        st.divider()

    # --- AUTO-REFRESH LOGIC ---
    is_user_waiting = queue_manager.get_queue_position(st.session_state.user_id) > 0
    is_system_processing = queue_manager.get_queue_stats()['processing'] > 0
    has_messages_to_process = len(queue_manager.message_queue) > 0

    if is_user_waiting or is_system_processing or has_messages_to_process:
        time.sleep(0.5)
        st.rerun()


if __name__ == "__main__":
    main()


