"""HTML-шаблоны писем UzAssets.

Оформление под фирменный стиль платформы (navy-хедер #0C1230→#111A3E,
бренд-фиолетовый #534AB7, моно код-бокс). Вёрстка email-safe: таблицы +
инлайн-стили (без внешнего CSS), чтобы корректно отображалось в Outlook/
Gmail/Apple Mail. Каждый билдер возвращает (subject, html).
"""
from __future__ import annotations

from html import escape

from app.core.i18n import normalize_locale, tr

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


_FONT = "'Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
_MONO = "'SF Mono',ui-monospace,'Cascadia Mono',Consolas,Menlo,monospace"
_TEAL = "#1D9E75"


def _shell(*, eyebrow: str, title: str, inner_html: str, accent: str = _PURPLE,
           locale: str = "ru") -> str:
    """Премиальная обёртка письма: глубокий navy-хедер с маркой и градиент-
    акцентом (purple→teal, как фирменный знак EPT), просторная карточка, футер."""
    locale = normalize_locale(locale)
    html_lang = {
        "ru": "ru", "uz-latn": "uz-Latn", "uz-cyr": "uz-Cyrl", "en": "en",
    }[locale]
    platform_tagline = tr(
        "Единая платформа управления портфелем государственных активов", locale,
    )
    automatic_note = tr(
        "Автоматическое письмо — отвечать не нужно. Если действие выполнили не вы — обратитесь к администратору платформы.",
        locale,
    )
    return f"""\
<!DOCTYPE html>
<html lang="{html_lang}"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light"></head>
<body style="margin:0;padding:0;background:#EEF0FF;-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">UzAssets · {escape(title)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF0FF;background:linear-gradient(180deg,#EEF0FF 0%,#F4F2FF 100%);padding:36px 14px;">
<tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 24px 64px rgba(15,23,60,.16),0 6px 18px rgba(15,23,60,.06);">
    <!-- Header -->
    <tr><td style="background:linear-gradient(135deg,{_NAVY_1} 0%,{_NAVY_2} 100%);padding:30px 36px 26px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="vertical-align:middle;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,{_PURPLE_L} 0%,{_TEAL} 100%);text-align:center;vertical-align:middle;font-family:{_FONT};font-size:15px;font-weight:800;color:#fff;">U</td>
            <td style="padding-left:12px;font-family:{_FONT};font-size:19px;font-weight:700;letter-spacing:-.02em;color:#ffffff;">UzAssets</td>
          </tr></table>
        </td>
        <td align="right" style="vertical-align:middle;">
          <span style="display:inline-block;padding:5px 12px;border-radius:20px;background:rgba(255,255,255,.10);font-family:{_FONT};font-size:9.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.78);">{escape(eyebrow)}</span>
        </td>
      </tr></table>
    </td></tr>
    <!-- Gradient accent bar (purple→teal) -->
    <tr><td style="height:4px;background:linear-gradient(90deg,{_PURPLE} 0%,{_PURPLE_L} 45%,{accent} 100%);font-size:0;line-height:0;">&nbsp;</td></tr>
    <!-- Content -->
    <tr><td style="padding:38px 36px 30px;font-family:{_FONT};">
      <h1 style="margin:0 0 20px;font-size:23px;font-weight:700;letter-spacing:-.025em;line-height:1.25;color:{_T1};">{escape(title)}</h1>
      {inner_html}
    </td></tr>
    <!-- Footer -->
    <tr><td style="padding:22px 36px 28px;border-top:1px solid {_BORDER};background:#FCFCFE;font-family:{_FONT};">
      <p style="margin:0 0 4px;font-size:11.5px;font-weight:600;color:{_T2};letter-spacing:.01em;">UzAssets · {escape(platform_tagline)}</p>
      <p style="margin:0;font-size:10.5px;line-height:1.6;color:{_T3};">{escape(automatic_note)}</p>
    </td></tr>
  </table>
  <p style="max-width:560px;margin:18px auto 0;font-family:{_FONT};font-size:10.5px;color:#9AA0B8;text-align:center;letter-spacing:.02em;">
    © UzAssets · platform.uz-assets.uz
  </p>
</td></tr></table>
</body></html>"""


def _p(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:14px;line-height:1.65;color:{_T2};">{text}</p>'


def _code_box(code: str) -> str:
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 22px;">
<tr><td style="background:linear-gradient(135deg,#F7F6FF 0%,#F0F3FF 100%);border:1px solid #E4E2FB;border-radius:14px;padding:24px 20px;text-align:center;">
  <div style="font-family:{_MONO};font-size:34px;font-weight:700;letter-spacing:.22em;color:{_T1};text-indent:.22em;">{escape(code)}</div>
</td></tr></table>"""


def _button(label: str, url: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 20px;"><tr>
<td style="border-radius:11px;background:linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%);box-shadow:0 6px 18px rgba(108,92,231,.34);">
  <a href="{escape(url)}" style="display:inline-block;padding:14px 32px;font-family:{_FONT};font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;letter-spacing:.01em;">{escape(label)}&nbsp;&rarr;</a>
</td></tr></table>"""


def _kv(label: str, value: str) -> str:
    return (f'<tr>'
            f'<td style="padding:9px 0;border-bottom:1px solid #F1F1F7;font-size:12px;color:{_T3};width:140px;vertical-align:top;">{escape(label)}</td>'
            f'<td style="padding:9px 0;border-bottom:1px solid #F1F1F7;font-size:13px;color:{_T1};font-weight:600;">{escape(value)}</td>'
            f'</tr>')


# ── Готовые письма ───────────────────────────────────────────────────

def mfa_code_email(*, code: str, email: str, ip: str | None = None,
                   when: str | None = None, locale: str = "ru") -> tuple[str, str]:
    locale = normalize_locale(locale)
    meta = "".join(filter(None, [
        _kv(tr("Аккаунт", locale), email),
        _kv(tr("IP-адрес", locale), ip) if ip else "",
        _kv(tr("Время", locale), when) if when else "",
    ]))
    inner = (
        _p(tr("Ваш одноразовый код для входа на платформу UzAssets:", locale))
        + _code_box(code)
        + _p(tr("Код действителен <b>5 минут</b>. Никому не сообщайте его — сотрудники UzAssets никогда не запрашивают код.", locale))
        + f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:6px;">{meta}</table>'
    )
    html = _shell(
        eyebrow=tr("Код доступа", locale),
        title=tr("Код подтверждения входа", locale),
        inner_html=inner, accent=_NAVY_2, locale=locale,
    )
    return (tr("UzAssets · код доступа", locale), html)


def invite_email(*, full_name: str, email: str, temp_password: str,
                 login_url: str, must_change: bool = True,
                 locale: str = "ru") -> tuple[str, str]:
    locale = normalize_locale(locale)
    inner = (
        _p(tr(
            "Здравствуйте, <b>{full_name}</b>! Для вас создан доступ к платформе UzAssets.",
            locale, full_name=escape(full_name),
        ))
        + f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 14px;">'
        + _kv(tr("Логин (email)", locale), email)
        + "</table>"
        + _p(tr("Временный пароль:", locale))
        + _code_box(temp_password)
        + (_p(tr("При первом входе система попросит <b>сменить пароль</b>.", locale)) if must_change else "")
        + _button(tr("Войти на платформу", locale), login_url)
        + _p(f'<span style="color:{_T3};font-size:12px;">{tr("Если кнопка не работает, откройте ссылку: {url}", locale, url=escape(login_url))}</span>')
    )
    html = _shell(
        eyebrow=tr("Приглашение", locale),
        title=tr("Доступ к платформе UzAssets", locale),
        inner_html=inner, locale=locale,
    )
    return (tr("UzAssets · доступ к платформе", locale), html)


def password_reset_email(*, full_name: str, reset_url: str,
                         valid_minutes: int = 30,
                         locale: str = "ru") -> tuple[str, str]:
    locale = normalize_locale(locale)
    inner = (
        _p(tr(
            "Здравствуйте, <b>{full_name}</b>. Мы получили запрос на сброс пароля для вашего аккаунта UzAssets.",
            locale, full_name=escape(full_name),
        ))
        + _button(tr("Сбросить пароль", locale), reset_url)
        + _p(tr(
            "Ссылка действительна <b>{minutes} минут</b>. Если вы не запрашивали сброс — просто проигнорируйте письмо, пароль останется прежним.",
            locale, minutes=valid_minutes,
        ))
        + _p(f'<span style="color:{_T3};font-size:12px;">{tr("Если кнопка не работает, откройте ссылку: {url}", locale, url=escape(reset_url))}</span>')
    )
    html = _shell(
        eyebrow=tr("Сброс пароля", locale),
        title=tr("Восстановление доступа", locale),
        inner_html=inner, accent=_NAVY_2, locale=locale,
    )
    return (tr("UzAssets · сброс пароля", locale), html)


def notification_email(*, eyebrow: str, title: str, lines: list[str],
                       action_label: str | None = None, action_url: str | None = None,
                       accent: str = _PURPLE, meta: list[tuple[str, str]] | None = None,
                       locale: str = "ru") -> tuple[str, str]:
    """Письмо-уведомление (задачи, упоминания, дедлайны, модерация, рассылки)."""
    inner = "".join(_p(l) for l in lines)
    if meta:
        inner += '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 14px;">' \
                 + "".join(_kv(k, v) for k, v in meta) + "</table>"
    if action_label and action_url:
        inner += _button(action_label, action_url)
    html = _shell(
        eyebrow=eyebrow, title=title, inner_html=inner, accent=accent,
        locale=locale,
    )
    return (f"UzAssets · {title}", html)


def generic_email(*, eyebrow: str, title: str, body_lines: list[str],
                  button_label: str | None = None, button_url: str | None = None,
                  accent: str = _PURPLE, locale: str = "ru") -> tuple[str, str]:
    inner = "".join(_p(line) for line in body_lines)
    if button_label and button_url:
        inner += _button(button_label, button_url)
    html = _shell(
        eyebrow=eyebrow, title=title, inner_html=inner, accent=accent,
        locale=locale,
    )
    return (f"UzAssets · {title}", html)
