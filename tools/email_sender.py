"""
Email Sender for the AI Intelligence System.
Sends briefing reports via Gmail SMTP with optional Excel attachment.
"""

import os
import smtplib
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

BRIEFINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".tmp", "briefings")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def get_latest_briefing():
    """Find the most recent briefing file."""
    pattern = os.path.join(BRIEFINGS_DIR, "briefing_*.md")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return None, None
    filepath = files[0]
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return filepath, content


def markdown_to_html(md_text):
    """Simple markdown to HTML conversion for email rendering."""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue

        # Headers
        if stripped.startswith("# "):
            html_lines.append(f'<h1 style="color:#1a1a2e;border-bottom:2px solid #e94560;padding-bottom:8px;">{stripped[2:]}</h1>')
        elif stripped.startswith("## "):
            html_lines.append(f'<h2 style="color:#1a1a2e;margin-top:24px;">{stripped[3:]}</h2>')
        elif stripped.startswith("### "):
            html_lines.append(f'<h3 style="color:#16213e;">{stripped[4:]}</h3>')
        # List items
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item = stripped[2:]
            while "**" in item:
                item = item.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
            html_lines.append(f"<li>{item}</li>")
        # Horizontal rule
        elif stripped == "---":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
        # Italic line
        elif stripped.startswith("*") and stripped.endswith("*"):
            html_lines.append(f"<p><em>{stripped.strip('*')}</em></p>")
        else:
            text = stripped
            while "**" in text:
                text = text.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
            html_lines.append(f"<p>{text}</p>")

    if in_list:
        html_lines.append("</ul>")

    body = "\n".join(html_lines)

    return f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 max-width: 700px; margin: 0 auto; padding: 20px; color: #333; line-height: 1.6;">
    {body}
    </body>
    </html>
    """


def _build_message(subject, email_from, email_to, briefing_content, excel_path=None):
    """Build the email message with optional Excel attachment."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to

    # Body: HTML + plain text alternative
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(briefing_content, "plain", "utf-8"))
    body_part.attach(MIMEText(markdown_to_html(briefing_content), "html", "utf-8"))
    msg.attach(body_part)

    # Excel attachment
    if excel_path and os.path.exists(excel_path):
        with open(excel_path, "rb") as f:
            attachment = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        filename = os.path.basename(excel_path)
        attachment.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(attachment)

    return msg


def _send(msg, email_from, email_password, email_to):
    """Send message via SMTP."""
    print(f"  Connecting to {SMTP_SERVER}:{SMTP_PORT} as {email_from}...")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(email_from, email_password)
        server.sendmail(email_from, email_to, msg.as_string())


def send_briefing(filepath=None, content=None):
    """Send the briefing via email (no attachment)."""
    email_from = os.getenv("EMAIL_FROM")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_to = os.getenv("EMAIL_TO")

    if not all([email_from, email_password, email_to]):
        print("Error: EMAIL_FROM, EMAIL_PASSWORD, and EMAIL_TO must be set in .env")
        return False

    if not filepath or not content:
        filepath, content = get_latest_briefing()

    if not content:
        print("No briefing found. Run the briefing generator first.")
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"AI Intelligence Briefing - {date_str}"

    msg = _build_message(subject, email_from, email_to, content)

    try:
        _send(msg, email_from, email_password, email_to)
        print(f"Briefing sent to {email_to}")
        print(f"  Subject: {subject}")
        print(f"  Source: {filepath}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("Authentication failed. Check EMAIL_FROM and EMAIL_PASSWORD in .env.")
        print("For Gmail, make sure you're using an App Password, not your regular password.")
        return False
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_daily_report(briefing_path=None, excel_path=None):
    """Send the weekly briefing with Excel attachment."""
    email_from = os.getenv("EMAIL_FROM")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_to = os.getenv("EMAIL_TO")

    if not all([email_from, email_password, email_to]):
        print("Error: EMAIL_FROM, EMAIL_PASSWORD, and EMAIL_TO must be set as environment variables")
        print(f"  EMAIL_FROM: {'set' if email_from else 'MISSING'}")
        print(f"  EMAIL_PASSWORD: {'set' if email_password else 'MISSING'}")
        print(f"  EMAIL_TO: {'set' if email_to else 'MISSING'}")
        return False

    # Get briefing content
    if briefing_path and os.path.exists(briefing_path):
        with open(briefing_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        briefing_path, content = get_latest_briefing()

    if not content:
        print("No briefing found. Run the briefing generator first.")
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"Weekly AI Intelligence Report - {date_str}"

    msg = _build_message(subject, email_from, email_to, content, excel_path=excel_path)

    try:
        _send(msg, email_from, email_password, email_to)
        print(f"Report sent to {email_to}")
        print(f"  Subject: {subject}")
        print(f"  Briefing: {briefing_path}")
        if excel_path:
            print(f"  Excel attached: {os.path.basename(excel_path)}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("EMAIL FAILED: Authentication error. Check EMAIL_FROM and EMAIL_PASSWORD.")
        print("  For Gmail, make sure you're using an App Password, not your regular password.")
        return False
    except Exception as e:
        print(f"EMAIL FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    send_briefing()
