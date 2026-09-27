import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'webswarm.db')

def reset_database():
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return

    print(f"[*] Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # We DELETE FROM tables to preserve the schema structure.
        # We keep the 'users' table intact so logins continue to work.
        print("[*] Wiping 'vision_diffs' table...")
        cursor.execute("DELETE FROM vision_diffs")
        
        print("[*] Wiping 'reports' table...")
        cursor.execute("DELETE FROM reports")
        
        print("[*] Wiping 'bugs' table...")
        cursor.execute("DELETE FROM bugs")
        
        print("[*] Wiping 'test_runs' table...")
        cursor.execute("DELETE FROM test_runs")

        # Reset sqlite autoincrement sequences for these tables
        print("[*] Resetting AUTOINCREMENT counters...")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('vision_diffs', 'reports', 'bugs', 'test_runs')")

        conn.commit()
        print("[+] Success! All testing metrics, history, and bugs have been wiped clean.")
        print("[+] Schema and User accounts were preserved.")
    except Exception as e:
        print(f"[!] Error during database reset: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    confirm = input("WARNING: This will delete all test history and bugs. Type 'YES' to proceed: ")
    if confirm == "YES":
        reset_database()
    else:
        print("Aborted.")
