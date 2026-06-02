"""HTML-шаблоны писем UzAssets.

Оформление под фирменный стиль платформы (navy-хедер #0C1230→#111A3E,
бренд-фиолетовый #534AB7, моно код-бокс). Вёрстка email-safe: таблицы +
инлайн-стили (без внешнего CSS), чтобы корректно отображалось в Outlook/
Gmail/Apple Mail. Каждый билдер возвращает (subject, html).
"""
from __future__ import annotations

from html import escape

# ── Палитра (синхронизирована с дизайн-системой) ──
_NAVY_1 = "#0C1230"
_NAVY_2 = "#111A3E"
_PURPLE = "#534AB7"
_PURPLE_L = "#7C6FF7"
_T1 = "#1E2A4A"
_T2 = "#475569"
_T3 = "#8A93A6"
_BORDER = "#E5E7EB"
_BG = "#F4F2FF"


def _shell(*, eyebrow: str, title: str, inner_html: str, accent: str = _PURPLE) -> str:
    """Общая обёртка письма: navy-хедер с вордмаркой + карточка контента + футер."""
    return f"""\
<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting"></head>
<body style="margin:0;padding:0;background:{_BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:28px 12px;">
<tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 12px 40px rgba(15,23,60,.12);">
    <!-- Header -->
    <tr><td style="background:linear-gradient(135deg,{_NAVY_1} 0%,{_NAVY_2} 100%);padding:22px 28px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:17px;font-weight:700;letter-spacing:-.01em;color:#ffffff;">UzAssets</td>
        <td align="right" style="font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:rgba(255,255,255,.55);">{escape(eyebrow)}</td>
      </tr></table>
    </td></tr>
    <!-- Accent line -->
    <tr><td style="height:3px;background:{accent};font-size:0;line-height:0;">&nbsp;</td></tr>
    <!-- Content -->
    <tr><td style="padding:30px 28px 24px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
      <h1 style="margin:0 0 16px;font-size:19px;font-weight:600;letter-spacing:-.01em;color:{_T1};">{escape(title)}</h1>
      {inner_html}
    </td></tr>
    <!-- Footer -->
    <tr><td style="padding:18px 28px 24px;border-top:1px solid {_BORDER};font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
      <p style="margin:0;font-size:11px;line-height:1.5;color:{_T3};">
        Единая платформа управления портфелем государственных активов UzAssets.<br>
        Это автоматическое письмо — отвечать на него не нужно.
      </p>
    </td></tr>
  </table>
  <p style="max-width:520px;margin:14px auto 0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:10.5px;color:{_T3};text-align:center;">
    © UzAssets · platform.uz-assets.uz
  </p>
</td></tr></table>
</body></html>"""


def _p(text: str) -> str:
    return f'<p style="margin:0 0 12px;font-size:13.5px;line-height:1.6;color:{_T2};">{text}</p>'


def _code_box(code: str) -> str:
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;">
<tr><td style="background:{_BG};border:1px solid {_BORDER};border-left:4px solid {_PURPLE};border-radius:10px;padding:18px 20px;text-align:center;">
  <div style="font-family:'SF Mono',Consolas,Menlo,monospace;font-size:30px;font-weight:700;letter-spacing:.18em;color:{_T1};">{escape(code)}</div>
</td></tr></table>"""


def _button(label: str, url: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 18px;"><tr>
<td style="border-radius:9px;background:linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%);">
  <a href="{escape(url)}" style="display:inline-block;padding:11px 26px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:13.5px;font-weight:600;color:#ffffff;text-decoration:none;">{escape(label)}</a>
</td></tr></table>"""


def _kv(label: str, value: str) -> str:
    return (f'<tr><td style="padding:4px 0;font-size:12px;color:{_T3};width:130px;">{escape(label)}</td>'
            f'<td style="padding:4px 0;font-size:12.5px;color:{_T1};font-weight:500;">{escape(value)}</td></tr>')


# ── Готовые письма ───────────────────────────────────────────────────

def mfa_code_email(*, code: str, email: str, ip: str | None = None, when: str | None = None) -> tuple[str, str]:
    meta = "".join(filter(None, [
        _kv("Аккаунт", email),
        _kv("IP-адрес", ip) if ip else "",
        _kv("Время", when) if when else "",
    ]))
    inner = (
        _p("Ваш одноразовый код для входа на платформу UzAssets:")
        + _code_box(code)
        + _p("Код действителен <b>5 минут</b>. Никому не сообщайте его — сотрудники UzAssets никогда не запрашивают код.")
        + f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:6px;">{meta}</table>'
    )
    html = _shell(eyebrow="Код доступа", title="Код подтверждения входа", inner_html=inner, accent=_NAVY_2)
    return ("UzAssets · код доступа", html)


def invite_email(*, full_name: str, email: str, temp_password: str,
                 login_url: str, must_change: bool = True) -> tuple[str, str]:
    inner = (
        _p(f"Здравствуйте, <b>{escape(full_name)}</b>! Для вас создан доступ к платформе UzAssets.")
        + f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 14px;">'
        + _kv("Логин (email)", email)
        + "</table>"
        + _p("Временный пароль:")
        + _code_box(temp_password)
        + (_p("При первом входе система попросит <b>сменить пароль</b>.") if must_change else "")
        + _button("Войти на платформу", login_url)
        + _p(f'<span style="color:{_T3};font-size:12px;">Если кнопка не работает, откройте ссылку: {escape(login_url)}</span>')
    )
    html = _shell(eyebrow="Приглашение", title="Доступ к платформе UzAssets", inner_html=inner)
    return ("UzAssets · доступ к платформе", html)


def password_reset_email(*, full_name: str, reset_url: str,
                         valid_minutes: int = 30) -> tuple[str, str]:
    inner = (
        _p(f"Здравствуйте, <b>{escape(full_name)}</b>. Мы получили запрос на сброс пароля для вашего аккаунта UzAssets.")
        + _button("Сбросить пароль", reset_url)
        + _p(f"Ссылка действительна <b>{valid_minutes} минут</b>. Если вы не запрашивали сброс — просто проигнорируйте письмо, пароль останется прежним.")
        + _p(f'<span style="color:{_T3};font-size:12px;">Если кнопка не работает, откройте ссылку: {escape(reset_url)}</span>')
    )
    html = _shell(eyebrow="Сброс пароля", title="Восстановление доступа", inner_html=inner, accent=_NAVY_2)
    return ("UzAssets · сброс пароля", html)


def notification_email(*, eyebrow: str, title: str, lines: list[str],
                       action_label: str | None = None, action_url: str | None = None,
                       accent: str = _PURPLE, meta: list[tuple[str, str]] | None = None) -> tuple[str, str]:
    """Письмо-уведомление (задачи, упоминания, дедлайны, модерация, рассылки)."""
    inner = "".join(_p(l) for l in lines)
    if meta:
        inner += '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 14px;">' \
                 + "".join(_kv(k, v) for k, v in meta) + "</table>"
    if action_label and action_url:
        inner += _button(action_label, action_url)
    html = _shell(eyebrow=eyebrow, title=title, inner_html=inner, accent=accent)
    return (f"UzAssets · {title}", html)


def generic_email(*, eyebrow: str, title: str, body_lines: list[str],
                  button_label: str | None = None, button_url: str | None = None,
                  accent: str = _PURPLE) -> tuple[str, str]:
    inner = "".join(_p(line) for line in body_lines)
    if button_label and button_url:
        inner += _button(button_label, button_url)
    html = _shell(eyebrow=eyebrow, title=title, inner_html=inner, accent=accent)
    return (f"UzAssets · {title}", html)
