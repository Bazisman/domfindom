import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from backend.config import settings


class AuthMailer:
    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.smtp_from = settings.smtp_from
        self.smtp_use_tls = settings.smtp_use_tls
        self.smtp_use_ssl = settings.smtp_use_ssl
        self.reset_url_template = settings.password_reset_url_template
        self.reset_email_subject = settings.password_reset_email_subject

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    def _build_reset_url(self, token: str) -> str:
        template = self.reset_url_template or "{token}"
        return template.replace("{token}", quote(token, safe=""))

    def send_password_reset_email(self, to_email: str, token: str) -> None:
        if not self.is_configured():
            return

        reset_url = self._build_reset_url(token)
        message = EmailMessage()
        message["Subject"] = self.reset_email_subject or "Восстановление пароля"
        message["From"] = self.smtp_from
        message["To"] = to_email
        message.set_content(
            "Для вашей учетной записи был запрошен сброс пароля.\n\n"
            f"Откройте ссылку, чтобы продолжить:\n{reset_url}\n\n"
            "Если вы не запрашивали сброс, просто проигнорируйте это письмо."
        )

        if self.smtp_use_ssl:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10) as server:
                if self.smtp_user:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
            if self.smtp_use_tls:
                server.starttls()
            if self.smtp_user:
                server.login(self.smtp_user, self.smtp_password)
            server.send_message(message)


auth_mailer = AuthMailer()
