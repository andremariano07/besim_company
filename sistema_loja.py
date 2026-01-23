
# -*- coding: utf-8 -*-
"""
Sistema Loja - versão unificada com auto-update (após login), splash estilizada e barra de progresso real.
Garantias:
- Roda sem erro
- Atualiza apenas uma vez (sem loop) ✅ (compara remote VERSION com VERSION local)
- Splash bonita com logo (se existir) e SEMPRE em primeiro plano
- Barra de progresso real
- Login abre normalmente
- Banco (besim_company.db) nunca é sobrescrito
- Pronto para virar EXE (PyInstaller)
- Operadores lógicos somente em inglês (or / and / not)
- Um único APP_VERSION e um único __main__
- Melhoria: janela volta para frente após abrir PDF (bring_app_to_front)
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import sqlite3
import datetime
import calendar
import re
import os
import sys
import hashlib
import platform
import logging
import urllib.request
import tempfile
import zipfile
import shutil
import ssl
import glob
import certifi
from functools import partial
from reportlab.lib.pagesizes import A4
import smtplib
from email.message import EmailMessage
import os
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ===================== VISUAL KIT (Windows 11 dark / light) =====================
# Preferência: Modern Dark (grafite) com destaques azul/verde + toasts empilhados
try:
    import sv_ttk  # pip install sv-ttk
    _HAS_SV_TTK = True
except Exception:
    sv_ttk = None
    _HAS_SV_TTK = False

THEME_DARK = {
    "bg": "#1f1f1f",
    "panel": "#252526",
    "panel2": "#2b2b2b",
    "text": "#f2f2f2",
    "muted": "#c7c7c7",
    "border": "#3a3a3a",
    "accent": "#2563eb",   # azul
    "accent2": "#22c55e",  # verde
    "warn": "#f6c453",
    "danger": "#ef4444",
}

THEME_LIGHT = {
    "bg": "#f5f6f7",
    "panel": "#ffffff",
    "panel2": "#f3f4f6",
    "text": "#111827",
    "muted": "#4b5563",
    "border": "#e5e7eb",
    "accent": "#2563eb",
    "accent2": "#16a34a",
    "warn": "#d97706",
    "danger": "#dc2626",
}

BASE_FONT = ("Segoe UI", 10)
HEADING_FONT = ("Segoe UI", 11, "bold")
BUTTON_FONT = ("Segoe UI", 10, "bold")
PADX = 10
PADY = 8

# ================= ENVIO DE CUPOM POR E-MAIL (movido para topo) =================

def _load_email_config():
    """Lê email_config.txt (chaves: EMAIL_GMAIL, EMAIL_GMAIL_APP)."""
    cfg = {}
    try:
        import os
        path = os.path.join(os.getcwd(), "email_config.txt")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip()
    except Exception as ex:
        logging.error("Falha ao ler email_config.txt: " + str(ex))
    return cfg




def enviar_cupom_email(destinatario_email, caminho_pdf):
    """Envia o cupom por e-mail usando Gmail.
    Retorna (True, "OK") em caso de sucesso; em falha retorna (False, mensagem_detalhada)."""
    try:
        import smtplib
        from email.message import EmailMessage
        import datetime
        import os
        if not destinatario_email or "@" not in destinatario_email:
            msg = "E-mail do destinatário vazio ou inválido."
            logging.error(msg)
            return False, msg
        if not os.path.isfile(caminho_pdf):
            msg = f"Arquivo PDF não encontrado: {caminho_pdf}"
            logging.error(msg)
            return False, msg
        cfg = _load_email_config()
        EMAIL_REMETENTE = cfg.get("EMAIL_GMAIL") or os.getenv("EMAIL_GMAIL")
        SENHA_APP = cfg.get("EMAIL_GMAIL_APP") or os.getenv("EMAIL_GMAIL_APP")
        if not EMAIL_REMETENTE or not SENHA_APP:
            msg = ("Credenciais não configuradas. Configure EMAIL_GMAIL e EMAIL_GMAIL_APP em "
                   "email_config.txt ou variáveis de ambiente.")
            logging.error(msg)
            return False, msg
        msg_obj = EmailMessage()
        msg_obj["Subject"] = "Seu cupom de compra - BESIM COMPANY"
        msg_obj["From"] = EMAIL_REMETENTE
        msg_obj["To"] = destinatario_email
        msg_obj["Date"] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S')
        msg_obj.set_content("""Olá!
Segue em anexo o cupom da sua compra.
Obrigado pela preferência!""")
        with open(caminho_pdf, "rb") as fpdf:
            msg_obj.add_attachment(
                fpdf.read(), maintype="application", subtype="pdf",
                filename=os.path.basename(caminho_pdf)
            )
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                smtp.login(EMAIL_REMETENTE, SENHA_APP)
                smtp.send_message(msg_obj)
                return True, "OK"
        except smtplib.SMTPAuthenticationError as e:
            logging.error("Falha de autenticação SMTP: %s", str(e))
            return False, f"Autenticação SMTP falhou: {e}"
        except Exception as e_ssl:
            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(EMAIL_REMETENTE, SENHA_APP)
                    smtp.send_message(msg_obj)
                    return True, "OK"
            except Exception as e_tls:
                logging.error("Erro ao enviar e-mail (SSL e TLS falharam): %s | %s", str(e_ssl), str(e_tls))
                return False, f"Falha SSL/TLS: {e_ssl} | {e_tls}"
    except Exception as e:
        logging.error("Erro inesperado ao enviar e-mail: %s", str(e), exc_info=True)
        return False, f"Erro inesperado: {e}"

def garantir_pastas_backup():
    try:
        for pasta in ("banco", "cupons", "OS", "relatorios"):
            os.makedirs(os.path.join(GOOGLE_DRIVE_BACKUP, pasta), exist_ok=True)
    except Exception as ex:
        logging.error(f"Falha ao criar pastas de backup: {ex}", exc_info=True)
def backup_banco():
    try:
        garantir_pastas_backup()
        if os.path.exists(DB_PATH):
            agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            destino = os.path.join(
                GOOGLE_DRIVE_BACKUP, "banco", f"besim_company_{agora}.db"
            )
            shutil.copy2(DB_PATH, destino)
            logging.info(f"Backup do banco -> {destino}")
    except Exception as ex:
        logging.error(f"Falha no backup do DB: {ex}", exc_info=True)
def backup_pdf(caminho_pdf: str, tipo: str):
    try:
        garantir_pastas_backup()
        destino_dir = os.path.join(GOOGLE_DRIVE_BACKUP, tipo)
        os.makedirs(destino_dir, exist_ok=True)
        if os.path.exists(caminho_pdf):
            shutil.copy2(caminho_pdf, destino_dir)
            logging.info(
                f"Backup PDF ({tipo}) -> {os.path.join(destino_dir, os.path.basename(caminho_pdf))}"
            )
    except Exception as ex:
        logging.error(f"Falha no backup PDF: {ex}", exc_info=True)
def backup_bulk_dir(local_dir: str, tipo: str):
    try:
        garantir_pastas_backup()
        destino_dir = os.path.join(GOOGLE_DRIVE_BACKUP, tipo)
        os.makedirs(destino_dir, exist_ok=True)
        if os.path.exists(local_dir):
            for pdf in glob.glob(os.path.join(local_dir, "*.pdf")):
                shutil.copy2(pdf, destino_dir)
            logging.info(f"Backup em lote de {local_dir} -> {destino_dir}")
    except Exception as ex:
        logging.error(f"Falha no backup em lote: {ex}", exc_info=True)
# ===================== CONFIGURAÇÕES =====================
DISABLE_AUTO_UPDATE = DISABLE_AUTO_UPDATE = (
    False # <-- Evita que a atualização automática sobrescreva este patch
)
APP_VERSION = "3.4"
OWNER = "andremariano07"
REPO = "besim_company"
BRANCH = "main"
VERSION_FILE = "VERSION"
DB_PATH = "besim_company.db"
IGNORE_FILES = {"besim_company.db"}
IGNORE_DIRS = {"cupons", "relatorios", "OS", "__pycache__", ".git"}
# ===================== LOG =====================
LOG_FILE = "sistema_loja_errors.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
# ===================== BANCO =====================
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS clientes (
    cpf TEXT PRIMARY KEY,
    nome TEXT,
    telefone TEXT
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS produtos (
    codigo TEXT PRIMARY KEY,
    nome TEXT,
    tipo TEXT,
    custo REAL,
    preco REAL,
    estoque INTEGER
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    cpf TEXT,
    produto TEXT,
    quantidade INTEGER,
    total REAL,
    pagamento TEXT,
    data TEXT,
    hora TEXT
)
"""
)
# >>> ATUALIZADO: tabela caixa já contempla hora e motivo para novos bancos
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL,
    data TEXT,
    hora TEXT,
    motivo TEXT
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS fechamento_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT UNIQUE,
    total REAL
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS manutencao (
    os INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT,
    nome TEXT,
    telefone TEXT,
    descricao TEXT,
    data TEXT,
    valor REAL DEFAULT 0,
    aprovado INTEGER DEFAULT 0
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT,
    is_admin INTEGER DEFAULT 0
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS devolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT,
    motivo TEXT,
    nome TEXT,
    data TEXT,
    hora TEXT
)
"""
)
conn.commit()
# >>> NOVO: agendamento de retirada de celulares
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS agendamentos_celulares (
    data_iso TEXT PRIMARY KEY,
    responsavel TEXT,
    atualizado_em TEXT
)
"""
)
conn.commit()

# ====== UTIL: hash de senha / migrações ======
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()
def ensure_is_admin_column():
    try:
        cursor.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cursor.fetchall()]
        if "is_admin" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass
ensure_is_admin_column()


def ensure_admin_user():
    try:
        cursor.execute("SELECT username, is_admin, COALESCE(password_last_changed,'') FROM users WHERE username=?", ("admin",))
        r = cursor.fetchone()
        today = datetime.datetime.now().strftime("%d/%m/%Y")
        if not r:
            admin_hash = hash_password("admin123")
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin, password_last_changed) VALUES (?,?,1,?)",
                ("admin", admin_hash, today)
            )
            cursor.execute(
                "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                ("admin", admin_hash, today)
            )
            conn.commit()
        else:
            if r[1] != 1:
                cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", ("admin",))
            if not r[2]:
                cursor.execute("SELECT password_hash FROM users WHERE username=?", ("admin",))
                cur_hash = cursor.fetchone()[0]
                cursor.execute("UPDATE users SET password_last_changed=? WHERE username=?", (today, "admin"))
                cursor.execute(
                    "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                    ("admin", cur_hash, today)
                )
            conn.commit()
    except Exception:
        pass

ensure_admin_user()

# >>> NOVO: migração segura das colunas hora/motivo da tabela caixa (para bancos existentes)
def ensure_caixa_columns():
    try:
        cursor.execute("PRAGMA table_info(caixa)")
        cols = {c[1] for c in cursor.fetchall()}
        altered = False
        if "hora" not in cols:
            cursor.execute("ALTER TABLE caixa ADD COLUMN hora TEXT")
            altered = True
        if "motivo" not in cols:
            cursor.execute("ALTER TABLE caixa ADD COLUMN motivo TEXT")
            altered = True
        if altered:
            conn.commit()
    except Exception:
        pass
ensure_caixa_columns()


def ensure_password_policy_tables():
    # Tabela de histórico de senhas (uma entrada por troca)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS user_password_history (
        username TEXT,
        password_hash TEXT,
        changed_at TEXT,
        PRIMARY KEY (username, changed_at)
    )
    """
    )
    # Adiciona coluna 'password_last_changed' na tabela users, se ainda não existir
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "password_last_changed" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN password_last_changed TEXT")
        conn.commit()

ensure_password_policy_tables()

# Utilitários de política de senha (30 dias + últimas 3)
def _parse_br_date(d: str):
    try:
        return datetime.datetime.strptime(d, "%d/%m/%Y").date()
    except Exception:
        return None

def days_since_last_change(username: str) -> int:
    try:
        cursor.execute("SELECT password_last_changed FROM users WHERE username=?", (username,))
        d = cursor.fetchone()
        if not d or not d[0]:
            return 9999
        dt = _parse_br_date(d[0])
        if not dt:
            return 9999
        return (datetime.date.today() - dt).days
    except Exception:
        return 9999

def get_last_password_hashes(username: str, n: int = 3):
    cursor.execute(
        "SELECT password_hash FROM user_password_history WHERE username=? ORDER BY date(substr(changed_at,7,4)||'-'||substr(changed_at,4,2)||'-'||substr(changed_at,1,2)) DESC",
        (username,)
    )
    rows = cursor.fetchall()
    return [r[0] for r in rows[:n]]

def password_reuse_forbidden(username: str, new_hash: str, n: int = 3) -> bool:
    return new_hash in get_last_password_hashes(username, n)

def set_new_password(username: str, new_plain: str):
    new_hash = hash_password(new_plain)
    if password_reuse_forbidden(username, new_hash, 3):
        raise ValueError("A nova senha não pode repetir nenhuma das últimas 3 senhas.")
    today = datetime.datetime.now().strftime("%d/%m/%Y")
    with conn:
        cursor.execute("UPDATE users SET password_hash=?, password_last_changed=? WHERE username=?", (new_hash, today, username))
        cursor.execute(
            "INSERT OR REPLACE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
            (username, new_hash, today)
        )
def is_admin(username: str) -> bool:
    try:
        cursor.execute("SELECT is_admin FROM users WHERE username=?", (username,))
        r = cursor.fetchone()
        return bool(r and r[0] == 1)
    except Exception:
        return False
# ===================== EXCEPTIONS TK (assinatura corrigida) =====================
def setup_global_exception_handlers(tk_root: tk.Misc):
    def excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            msg = f"Ocorreu um erro inesperado:\n{exc_value}\n\nDetalhes foram gravados em: {LOG_FILE}"
            messagebox.showerror("Erro inesperado", msg)
        except Exception:
            pass
    sys.excepthook = excepthook
    # Assinatura correta para Tkinter: (exc, val, tb)
    def tk_callback_exception(exc, val, tb):
        logging.error("Tkinter callback exception", exc_info=(exc, val, tb))
        try:
            msg = f"Ocorreu um erro na interface:\n{val}\n\nDetalhes foram gravados em: {LOG_FILE}"
            messagebox.showerror("Erro na interface", msg)
        except Exception:
            pass
    try:
        tk_root.report_callback_exception = tk_callback_exception
    except Exception:
        pass
# ===================== FOCO PÓS-PDF =====================
def bring_app_to_front():
    """Recoloca a janela do app na frente após abrir viewer externo."""
    try:
        root = tk._default_root
        if root and root.winfo_exists():
            root.lift()
            root.focus_force()
            try:
                root.attributes("-topmost", True)
                root.after(200, lambda: root.attributes("-topmost", False))
            except Exception:
                pass
    except Exception:
        pass


# ===================== TOAST (não-bloqueante) — Premium + Empilhado =====================
_ACTIVE_TOAST_ROOT = None

def _resolve_toast_base(parent=None):
    """Escolhe a melhor janela base para posicionar o toast."""
    try:
        if parent is not None and hasattr(parent, 'winfo_exists') and parent.winfo_exists():
            return parent
    except Exception:
        pass
    try:
        base = _ACTIVE_TOAST_ROOT
        if base is not None and hasattr(base, 'winfo_exists') and base.winfo_exists():
            return base
    except Exception:
        pass
    try:
        base = getattr(tk, '_default_root', None)
        if base is None or not hasattr(base, 'winfo_exists') or not base.winfo_exists():
            return None
        # Se a root estiver escondida, tenta achar algum Toplevel visível
        try:
            if str(base.state()) == 'withdrawn':
                for w in reversed(base.winfo_children()):
                    try:
                        if isinstance(w, tk.Toplevel) and w.winfo_exists() and str(w.state()) != 'withdrawn':
                            return w
                    except Exception:
                        pass
        except Exception:
            pass
        return base
    except Exception:
        return None


def _toast_level_from_title(title) -> str:
    """Heurística simples para escolher level do toast a partir do título."""
    try:
        t = str(title or '').strip().lower()
        if any(k in t for k in ('erro', 'falha')):
            return 'error'
        if any(k in t for k in ('atenção', 'atencao', 'aviso', 'warn')):
            return 'warn'
        if any(k in t for k in ('sucesso', 'ok', 'aprovado', 'upgrade', 'os', 'devolução', 'saida', 'saída', 'venda', 'cliente', 'produto', 'fechar', 'caixa')):
            return 'ok'
        return 'info'
    except Exception:
        return 'info'


def _toast_icon(level: str) -> str:
    return {'ok': '✅', 'warn': '⚠️', 'error': '❌', 'info': 'ℹ️'}.get(level or 'info', 'ℹ️')


def _get_toast_colors(level: str):
    # Paleta moderna escura por padrão
    base_bg = "#1f1f1f"
    colors = {
        'info': (base_bg, '#9cdcfe', '#2563eb'),
        'ok': (base_bg, '#c7f9cc', '#22c55e'),
        'warn': (base_bg, '#ffe8b5', '#f6c453'),
        'error': (base_bg, '#ffd1d1', '#ef4444'),
    }
    return colors.get(level, colors['info'])


def _reposition_toasts(base, anchor='top-right', margin=16, gap=10):
    """Recalcula posição de todos os toasts empilhados."""
    try:
        stack = getattr(base, '_toast_stack', []) or []
        stack = [w for w in stack if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
        base._toast_stack = stack
        if not stack:
            return
        base.update_idletasks()
        rx = base.winfo_rootx()
        ry = base.winfo_rooty()
        rw = base.winfo_width()
        if rw <= 1:
            rw = max(base.winfo_screenwidth(), 800)
        y = ry + margin
        for win in stack:
            try:
                win.update_idletasks()
                w = win.winfo_width()
                h = win.winfo_height()
                if anchor == 'top':
                    x = rx + (rw // 2) - (w // 2)
                else:
                    x = rx + rw - w - margin
                win.geometry(f'+{x}+{y}')
                y += h + gap
            except Exception:
                pass
    except Exception:
        pass


def show_toast(root: tk.Misc = None, text: str = '', level: str = 'info', duration_ms: int = 3500,
               anchor: str = 'top-right', max_stack: int = 4):
    """Mostra uma notificação tipo toast (não bloqueia a UI) — empilhado (2–4)."""
    global _ACTIVE_TOAST_ROOT
    try:
        base = _resolve_toast_base(root)
        if base is None:
            return
        _ACTIVE_TOAST_ROOT = base

        stack = getattr(base, '_toast_stack', []) or []
        stack = [w for w in stack if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
        base._toast_stack = stack

        while len(stack) >= int(max_stack):
            try:
                old = stack.pop(0)
                if old and old.winfo_exists():
                    old.destroy()
            except Exception:
                pass

        bg, fg, bar = _get_toast_colors(level)
        icon = _toast_icon(level)

        win = tk.Toplevel(base)
        win.overrideredirect(True)
        try:
            win.attributes('-topmost', True)
        except Exception:
            pass
        try:
            win.attributes('-alpha', 0.0)
        except Exception:
            pass

        shadow = tk.Frame(win, bg="#000000", bd=0, highlightthickness=0)
        shadow.pack(fill='both', expand=True)
        outer = tk.Frame(shadow, bg=bg, bd=0, highlightthickness=1, highlightbackground="#3a3a3a")
        outer.pack(padx=2, pady=2)

        tk.Frame(outer, bg=bar, width=6).pack(side='left', fill='y')
        body = tk.Frame(outer, bg=bg)
        body.pack(side='left', fill='both', expand=True)

        msg = f"{icon}  {text}".strip()
        tk.Label(body, text=msg, bg=bg, fg=fg, font=("Segoe UI", 10, "bold"), justify='left', anchor='w').pack(
            padx=12, pady=10
        )

        win.update_idletasks()
        stack.append(win)
        base._toast_stack = stack
        _reposition_toasts(base, anchor=anchor)

        # animação (fade + slide leve)
        try:
            cur_geo = win.geometry()
            mm = re.match(r"\d+x\d+\+(\-?\d+)\+(\-?\d+)", cur_geo)
            if mm:
                tx, ty = int(mm.group(1)), int(mm.group(2))
            else:
                tx, ty = win.winfo_x(), win.winfo_y()
            start_y = ty - 12
        except Exception:
            tx, ty, start_y = win.winfo_x(), win.winfo_y(), win.winfo_y() - 12

        def _anim_in(step=0):
            try:
                a = min(1.0, (step + 1) / 10)
                try:
                    win.attributes('-alpha', a)
                except Exception:
                    pass
                yy = int(start_y + (ty - start_y) * a)
                win.geometry(f'+{tx}+{yy}')
                if step < 9:
                    win.after(18, lambda: _anim_in(step + 1))
            except Exception:
                pass

        _anim_in(0)

        def _close():
            def _anim_out(step=0):
                try:
                    a = max(0.0, 1.0 - (step + 1) / 10)
                    try:
                        win.attributes('-alpha', a)
                    except Exception:
                        pass
                    if step < 9:
                        win.after(18, lambda: _anim_out(step + 1))
                    else:
                        try:
                            if win.winfo_exists():
                                win.destroy()
                        except Exception:
                            pass
                        try:
                            stack2 = getattr(base, '_toast_stack', []) or []
                            stack2 = [w for w in stack2 if w is not None and hasattr(w, 'winfo_exists') and w.winfo_exists()]
                            base._toast_stack = stack2
                            _reposition_toasts(base, anchor=anchor)
                        except Exception:
                            pass
                except Exception:
                    pass

            _anim_out(0)

        win.after(max(900, int(duration_ms)), _close)

    except Exception:
        pass


# Monkey patch: transforma todos os messagebox.showinfo em toast (sem mudar chamadas)
_ORIG_SHOWINFO = messagebox.showinfo

def _showinfo_toast(title, message, *args, **kwargs):
    try:
        parent = kwargs.get('parent')
        level = _toast_level_from_title(title)
        show_toast(parent, message, level=level, duration_ms=3500, anchor='top-right', max_stack=4)
    except Exception:
        pass
    return 'ok'

messagebox.showinfo = _showinfo_toast

# ===================== TOOLTIP (Micro UX) =====================
class ToolTip:
    """Tooltip simples para Tkinter/ttk."""
    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self.tip = None
        widget.bind('<Enter>', self._on_enter, add=True)
        widget.bind('<Leave>', self._on_leave, add=True)
        widget.bind('<ButtonPress>', self._on_leave, add=True)

    def _on_enter(self, _evt=None):
        self._schedule()

    def _on_leave(self, _evt=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _unschedule(self):
        try:
            if self._after_id:
                self.widget.after_cancel(self._after_id)
        except Exception:
            pass
        self._after_id = None

    def _show(self):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.tip = tk.Toplevel(self.widget)
            self.tip.overrideredirect(True)
            try:
                self.tip.attributes('-topmost', True)
            except Exception:
                pass
            frm = tk.Frame(self.tip, bg='#111827', highlightbackground='#374151', highlightthickness=1)
            frm.pack()
            lbl = tk.Label(frm, text=self.text, bg='#111827', fg='#f9fafb', font=('Segoe UI', 9), justify='left')
            lbl.pack(padx=10, pady=6)
            self.tip.geometry(f'+{x}+{y}')
        except Exception:
            self.tip = None

    def _hide(self):
        try:
            if self.tip and self.tip.winfo_exists():
                self.tip.destroy()
        except Exception:
            pass
        self.tip = None

def add_tooltip(widget, text: str):
    try:
        return ToolTip(widget, text)
    except Exception:
        return None


# ===================== TREEVIEW: Zebra (linhas alternadas) =====================
def configure_zebra_tags(tree: ttk.Treeview, theme_name: str = 'dark'):
    try:
        pal = THEME_DARK if theme_name == 'dark' else THEME_LIGHT
        even = pal['bg']
        odd = pal['panel'] if theme_name == 'dark' else pal['panel2']
        tree.tag_configure('even', background=even)
        tree.tag_configure('odd', background=odd)
    except Exception:
        pass

def apply_zebra(tree: ttk.Treeview):
    """Aplica zebra aos itens já inseridos (mantém outras tags)."""
    try:
        for i, iid in enumerate(tree.get_children('')):
            tags = list(tree.item(iid, 'tags') or [])
            tags = [t for t in tags if t not in ('even', 'odd')]
            tags.append('even' if i % 2 == 0 else 'odd')
            tree.item(iid, tags=tuple(tags))
    except Exception:
        pass

# ===================== SPLASH SCREEN (corrigida: primeiro plano garantido) =====================
class SplashScreen(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.geometry("520x300")
        self.configure(bg="#1e1e1e")
        # Centralização manual (Windows-safe)
        try:
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (520 // 2)
            y = (self.winfo_screenheight() // 2) - (300 // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        # Garantir visibilidade (reforços)
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(10, self.lift)
            self.after(20, lambda: self.attributes("-topmost", True))
            self.after(30, self.focus_force)
        except Exception:
            pass
        frame = tk.Frame(self, bg="#1e1e1e")
        frame.pack(expand=True, fill="both")
        logo_path = os.path.join(os.getcwd(), "logo.png")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((240, 80))
                self.logo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=self.logo, bg="#1e1e1e").pack(pady=(40, 20))
            except Exception:
                tk.Label(
                    frame,
                    text="BESIM COMPANY",
                    fg="white",
                    bg="#1e1e1e",
                    font=("Segoe UI", 20, "bold"),
                ).pack(pady=(55, 20))
        else:
            tk.Label(
                frame,
                text="BESIM COMPANY",
                fg="white",
                bg="#1e1e1e",
                font=("Segoe UI", 20, "bold"),
            ).pack(pady=(55, 20))
        tk.Label(
            frame,
            text="Atualizando sistema...",
            fg="#cccccc",
            bg="#1e1e1e",
            font=("Segoe UI", 12),
        ).pack()
        self.progress = ttk.Progressbar(
            frame, orient="horizontal", length=360, mode="determinate"
        )
        self.progress.pack(pady=25)
        self.status = tk.Label(
            frame,
            text="Preparando atualização",
            fg="#9cdcfe",
            bg="#1e1e1e",
            font=("Segoe UI", 10),
        )
        self.status.pack()
    def set_progress(self, value):
        self.progress["value"] = value
        try:
            self.update_idletasks()
        except Exception:
            pass
    def set_status(self, text):
        self.status.config(text=text)
        try:
            self.update_idletasks()
        except Exception:
            pass


def show_goodbye_screen(master, message="Até Logo,\nBom descanso", duration_ms=1500):
    """Mostra uma tela rápida de despedida com logo (se existir) e mensagem."""
    try:
        win = tk.Toplevel(master)
        win.overrideredirect(True)
        win.configure(bg="#1e1e1e")

        w, h = 520, 260
        try:
            win.update_idletasks()
            x = (win.winfo_screenwidth() // 2) - (w // 2)
            y = (win.winfo_screenheight() // 2) - (h // 2)
            win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            win.geometry(f"{w}x{h}")

        try:
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
        except Exception:
            pass

        frame = tk.Frame(win, bg="#1e1e1e")
        frame.pack(expand=True, fill="both")

        logo_path = os.path.join(os.getcwd(), "logo.png")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((240, 80))
                win._goodbye_logo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=win._goodbye_logo, bg="#1e1e1e").pack(pady=(35, 18))
            except Exception:
                tk.Label(
                    frame,
                    text="BESIM COMPANY",
                    fg="white",
                    bg="#1e1e1e",
                    font=("Segoe UI", 20, "bold"),
                ).pack(pady=(55, 18))
        else:
            tk.Label(
                frame,
                text="BESIM COMPANY",
                fg="white",
                bg="#1e1e1e",
                font=("Segoe UI", 20, "bold"),
            ).pack(pady=(55, 18))

        tk.Label(
            frame,
            text=message,
            fg="#9cdcfe",
            bg="#1e1e1e",
            font=("Segoe UI", 14, "bold"),
            justify="center",
            anchor="center",
        ).pack(pady=(0, 10))

        win.after(duration_ms, win.destroy)
        return win
    except Exception:
        return None
# ===================== UPDATE (após login, corrigido: sem loop) =====================

# >>> Diálogo modal de alteração de senha e atalhos de tela cheia
class ChangePasswordDialog(tk.Toplevel):
    def __init__(self, master, username: str, must_change: bool = False):
        super().__init__(master)
        self.title("Alterar Senha")
        self.resizable(False, False)
        self.username = username
        self.must_change = must_change
        self.result = False
        self.grab_set()
        self.transient(master)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        msg = "Sua senha expirou. Defina uma nova senha." if must_change else "Defina a nova senha."
        ttk.Label(frm, text=msg).pack(anchor="w", pady=(0,8))
        ttk.Label(frm, text="Nova senha").pack(anchor="w")
        self.ent_new = ttk.Entry(frm, show="*")
        self.ent_new.pack(fill="x", pady=4)
        ttk.Label(frm, text="Confirmar nova senha").pack(anchor="w")
        self.ent_conf = ttk.Entry(frm, show="*")
        self.ent_conf.pack(fill="x", pady=4)
        ttk.Label(frm, text="Não é permitido reutilizar as últimas 3 senhas.").pack(anchor="w", pady=(6,2))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="right", padx=6)
        ttk.Button(btns, text="Salvar", style="Success.TButton", command=self._save).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self._save())
        if must_change:
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        else:
            self.protocol("WM_DELETE_WINDOW", self._cancel)
    def _save(self):
        new = (self.ent_new.get() or "").strip()
        conf = (self.ent_conf.get() or "").strip()
        if len(new) < 6:
            messagebox.showwarning("Atenção", "A senha deve ter pelo menos 6 caracteres.")
            return
        if new != conf:
            messagebox.showerror("Erro", "As senhas digitadas não conferem.")
            return
        try:
            set_new_password(self.username, new)
            messagebox.showinfo("OK", "Senha alterada com sucesso!")
            self.result = True
            self.destroy()
        except ValueError as ve:
            messagebox.showerror("Erro", str(ve))
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao alterar a senha\n{ex}")
    def _cancel(self):
        self.result = False
        self.destroy()

# Helper para alternar tela cheia (F11) e sair (Esc)
def _bind_fullscreen_shortcuts(win: tk.Misc):
    if not hasattr(win, "_is_fullscreen"):
        win._is_fullscreen = False
    def _toggle_fullscreen(evt=None):
        try:
            win._is_fullscreen = not getattr(win, "_is_fullscreen", False)
            win.attributes("-fullscreen", win._is_fullscreen)
        except Exception:
            try:
                win.state("zoomed" if win._is_fullscreen else "normal")
            except Exception:
                pass
    def _exit_fullscreen(evt=None):
        try:
            win._is_fullscreen = False
            win.attributes("-fullscreen", False)
        except Exception:
            try:
                win.state("normal")
            except Exception:
                pass
    win.bind("<F11>", _toggle_fullscreen)
    win.bind("<Escape>", _exit_fullscreen)

def get_local_version() -> str:
    """Lê a versão local a partir do arquivo VERSION, se existir; senão usa APP_VERSION."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return APP_VERSION
def obter_versao_remota() -> str:
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{VERSION_FILE}"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=10) as r:
        return r.read().decode("utf-8").strip()
def baixar_e_extrair(splash: SplashScreen, remote_version: str):
    zip_url = f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip"
    temp_dir = tempfile.mkdtemp(prefix="update_")
    zip_path = os.path.join(temp_dir, "repo.zip")
    splash.set_status("Baixando atualização...")
    splash.set_progress(5)
    with urllib.request.urlopen(zip_url, context=_SSL_CTX) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        with open(zip_path, "wb") as out:
            while True:
                data = response.read(8192)
                if not data:
                    break
                out.write(data)
                downloaded += len(data)
                if total:
                    splash.set_progress(5 + int((downloaded / total) * 60))
    splash.set_status("Extraindo arquivos...")
    splash.set_progress(70)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_dir)
    splash.set_status("Copiando nova versão...")
    splash.set_progress(85)
    src_dir = next(os.scandir(temp_dir)).path
    for root_dir, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel = os.path.relpath(root_dir, src_dir)
        dest = os.path.join(os.getcwd(), rel)
        os.makedirs(dest, exist_ok=True)
        for f in files:
            if f not in IGNORE_FILES:
                shutil.copy2(os.path.join(root_dir, f), os.path.join(dest, f))
    # Garante que a versão local fique igual à remota
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as vf:
            vf.write(remote_version)
    except Exception:
        pass
    splash.set_status("Finalizando...")
    splash.set_progress(100)
def check_and_update_after_login(master: tk.Misc) -> bool:
    """Retorna True se atualizar (e reiniciar), False caso contrário."""
    if DISABLE_AUTO_UPDATE:
        return False
    try:
        remote_version = obter_versao_remota()
        local_version = get_local_version()
        if remote_version == local_version:
            return False # Já está na última versão
    except Exception as e:
        logging.error(f"Falha ao checar versão remota: {e}")
        return False
    try:
        # Esconde a janela principal ANTES da splash
        try:
            master.withdraw()
            master.update_idletasks()
            master.update()
        except Exception:
            pass
        splash = SplashScreen(master)
        try:
            splash.update()
        except Exception:
            pass
        baixar_e_extrair(splash, remote_version)
        splash.set_status("Atualização concluída. Reiniciando...")
        # Reforçar visibilidade antes do reinício
        try:
            splash.lift()
            splash.focus_force()
            splash.update()
        except Exception:
            pass
        master.after(
            1200, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)
        )
        try:
            splash.update()
        except Exception:
            pass
        master.mainloop()
        return True
    except Exception as e:
        logging.error(f"Falha na atualização automática: {e}", exc_info=True)
        try:
            messagebox.showerror("Erro", "Falha na atualização automática")
        except Exception:
            pass
        return False
# ================= FUNÇÕES PDF =================
def gerar_cupom(cliente, produto, qtd, pagamento, total):
    agora = datetime.datetime.now()
    pasta_cupons = os.path.join(os.getcwd(), "cupons")
    os.makedirs(pasta_cupons, exist_ok=True)
    nome_arquivo = os.path.join(
        pasta_cupons, f"cupom_{agora.strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(
                ImageReader(logo_path),
                40,
                730,
                width=150,
                height=50,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY",
        "----------------------------------------------"
        "----------------------------------------------",
        f"Cliente: {cliente}",
        f"Produto: {produto}",
        f"Quantidade: {qtd}",
        f"Forma de Pagamento: {pagamento}",
        f"Total: R$ {total:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        f"Hora: {agora.strftime('%H:%M:%S')}",
        "----------------------------------------------"
        "----------------------------------------------",
        "Obrigado pela preferência!",
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        backup_pdf(nome_arquivo, "cupons")
    except Exception:
        pass
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(nome_arquivo)
        elif sistema == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")
    except Exception:
        pass
    bring_app_to_front()
    return nome_arquivo

def gerar_os_pdf(os_num, nome, cpf, telefone, descricao, valor):
    agora = datetime.datetime.now()
    pasta_os = os.path.join(os.getcwd(), "OS")
    os.makedirs(pasta_os, exist_ok=True)
    nome_arquivo = os.path.join(pasta_os, f"OS_{os_num}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(
                ImageReader(logo_path),
                40,
                730,
                width=150,
                height=50,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY - ORDEM DE SERVIÇO",
        "----------------------------------------------"
        "----------------------------------------------",
        f"OS Nº: {os_num}",
        f"Cliente: {nome}",
        f"CPF: {cpf}",
        f"Telefone: {telefone}",
        f"Descrição: {descricao}",
        f"Valor: R$ {valor:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        "----------------------------------------------"
        "----------------------------------------------",
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
    try:
        backup_pdf(nome_arquivo, "OS")
    except Exception:
        pass
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(nome_arquivo)
        elif sistema == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")
    except Exception:
        pass
    bring_app_to_front()
# ================= RELATÓRIO VENDAS (PDF) =================
def gerar_relatorio_vendas_dia_pdf(data_str: str = None):
    hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    data_alvo = data_str or hoje
    pasta_rel = os.path.join(os.getcwd(), "relatorios")
    os.makedirs(pasta_rel, exist_ok=True)
    nome_arquivo = os.path.join(
        pasta_rel, f"relatorio_vendas_{data_alvo.replace('/', '-')}" + ".pdf"
    )
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path_local = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path_local):
        try:
            c.drawImage(
                ImageReader(logo_path_local),
                40,
                780,
                width=140,
                height=40,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
    c.setFont("Helvetica", 11)
    c.drawString(40, 742, "-" * 110)
    y = 720
    # Vendas do dia
    cursor.execute(
        "SELECT hora, cliente, produto, quantidade, pagamento, total FROM vendas WHERE data=? ORDER BY hora DESC",
        (data_alvo,),
    )
    linhas = cursor.fetchall()
    totais_pg = {"PIX": 0.0, "Cartão": 0.0, "Dinheiro": 0.0, "OUTROS": 0.0}
    total_dia = 0.0
    c.setFont("Helvetica", 10)
    if not linhas:
        c.drawString(40, y, "Nenhuma venda registrada neste dia.")
        y -= 18
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Hora")
        c.drawString(90, y, "Cliente")
        c.drawString(250, y, "Produto")
        c.drawString(420, y, "Qtd")
        c.drawString(455, y, "Pagto")
        c.drawString(520, y, "Total")
        y -= 16
        c.setFont("Helvetica", 10)
        for hora, cliente, produto, qtd, pagamento, total in linhas:
            total_dia += total or 0.0
            if pagamento in totais_pg:
                totais_pg[pagamento] += total or 0.0
            else:
                totais_pg["OUTROS"] += total or 0.0
            c.drawString(40, y, str(hora))
            c.drawString(90, y, str(cliente)[:24])
            c.drawString(250, y, str(produto)[:24])
            c.drawString(420, y, str(qtd))
            c.drawString(455, y, str(pagamento))
            c.drawRightString(590, y, f"R$ {float(total):.2f}")
            y -= 16
            if y < 60:
                c.showPage()
                if os.path.exists(logo_path_local):
                    try:
                        c.drawImage(
                            ImageReader(logo_path_local),
                            40,
                            780,
                            width=140,
                            height=40,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
                c.setFont("Helvetica", 11)
                c.drawString(40, 742, "-" * 110)
                y = 720
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, "Hora")
                c.drawString(90, y, "Cliente")
                c.drawString(250, y, "Produto")
                c.drawString(420, y, "Qtd")
                c.drawString(455, y, "Pagto")
                c.drawString(520, y, "Total")
                y -= 16
                c.setFont("Helvetica", 10)
    # Totais por forma de pagamento
    y -= 8
    c.setFont("Helvetica", 11)
    c.drawString(40, y, "-" * 110)
    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Totais por Forma de Pagamento:")
    y -= 18
    c.setFont("Helvetica", 11)
    for k in ["PIX", "Cartão", "Dinheiro", "OUTROS"]:
        c.drawString(40, y, f"{k}: R$ {totais_pg[k]:.2f}")
        y -= 18
    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total de vendas do dia: R$ {total_dia:.2f}")
    y -= 24
    # Saídas do dia
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Saídas do dia")
    y -= 18
    c.setFont("Helvetica", 11)
    # >>> Consulta compatível com colunas hora/motivo criadas na migração
    cursor.execute(
        "SELECT hora, motivo, valor FROM caixa WHERE data=? AND valor<0 ORDER BY hora DESC",
        (data_alvo,),
    )
    saidas = cursor.fetchall()
    total_saidas = 0.0
    if not saidas:
        c.drawString(40, y, "Nenhuma saída registrada neste dia.")
        y -= 18
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Hora")
        c.drawString(100, y, "Motivo")
        c.drawString(520, y, "Valor")
        y -= 16
        c.setFont("Helvetica", 10)
        for hora_s, motivo_s, valor_s in saidas:
            if y < 60:
                c.showPage()
                if os.path.exists(logo_path_local):
                    try:
                        c.drawImage(
                            ImageReader(logo_path_local),
                            40,
                            780,
                            width=140,
                            height=40,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
                c.setFont("Helvetica", 11)
                c.drawString(40, 742, "-" * 110)
                y = 720
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Saídas do dia (continuação)")
                y -= 18
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, "Hora")
                c.drawString(100, y, "Motivo")
                c.drawString(520, y, "Valor")
                y -= 16
                c.setFont("Helvetica", 10)
            hora_txt = str(hora_s or "--:--:--")
            motivo_txt = str(motivo_s or "(sem motivo)")[:48]
            c.drawString(40, y, hora_txt)
            c.drawString(100, y, motivo_txt)
            c.drawRightString(590, y, f"R$ {abs(float(valor_s)):.2f}")
            total_saidas += abs(float(valor_s))
            y -= 16
    # Resumo do caixa
    c.setFont("Helvetica", 11)
    c.drawString(40, y, "-" * 110)
    y -= 18
    cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (data_alvo,))
    total_liquido = cursor.fetchone()[0] or 0.0
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total de saídas: R$ {total_saidas:.2f}")
    y -= 18
    c.drawString(40, y, f"Total líquido do caixa: R$ {total_liquido:.2f}")
    c.save()
    try:
        backup_pdf(nome_arquivo, "relatorios")
    except Exception:
        pass
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(nome_arquivo)
        elif sistema == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")
    except Exception:
        pass
    bring_app_to_front()
    return nome_arquivo
# ================= FORMATAÇÃO CPF/TELEFONE/MOEDA =================
def formatar_cpf(event, entry):
    texto = "".join(filter(str.isdigit, entry.get()))[:11]
    novo = ""
    for i, c in enumerate(texto):
        if i == 3 or i == 6:
            novo += "."
        if i == 9:
            novo += "-"
        novo += c
    entry.delete(0, "end")
    entry.insert(0, novo)
def formatar_telefone(event, entry):
    texto = "".join(filter(str.isdigit, entry.get()))[:11]
    novo = ""
    for i, c in enumerate(texto):
        if i == 0:
            novo += "("
        if i == 2:
            novo += ") "
        if i == 7:
            novo += "-"
        novo += c
    entry.delete(0, "end")
    entry.insert(0, novo)
def formatar_moeda(event, entry):
    valor = entry.get().replace("R$", "").replace(",", ".").strip()
    if valor:
        try:
            valor_float = float(valor)
            entry.delete(0, "end")
            entry.insert(0, f"R$ {valor_float:.2f}")
        except Exception:
            entry.delete(0, "end")
            entry.insert(0, "R$ 0.00")
    else:
        entry.delete(0, "end")
        entry.insert(0, "")
# ================= SISTEMA PRINCIPAL =================
def abrir_sistema_com_logo(username, login_win):
    root = tk.Toplevel()
    root.title(f"BESIM COMPANY - Usuário: {username} ")
    root.geometry("1280x720")
    root.minsize(1100, 600)
    root.lift()
    root.focus_force()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    _bind_fullscreen_shortcuts(root)
    setup_global_exception_handlers(root)
    # Executa atualização após login (se houver)
    try:
        updated = check_and_update_after_login(root)
        if updated:
            return # app será reiniciado
    except Exception:
        pass
    closing_state = {"mode": None}

    def on_close():
        # 1) Logout: volta para o login sem mensagem de despedida
        if closing_state.get("mode") == "logout":
            try:
                root.destroy()
            except Exception:
                pass
            try:
                if login_win and login_win.winfo_exists():
                    login_win.deiconify()
                    login_win.lift()
                    login_win.focus_force()
                    if hasattr(login_win, "ent_user"):
                        login_win.ent_user.delete(0, "end")
                    if hasattr(login_win, "ent_pass"):
                        login_win.ent_pass.delete(0, "end")
            except Exception:
                pass
            closing_state["mode"] = None
            return

        # 2) Encerrar o programa: mostra despedida (duas linhas)
        if messagebox.askyesno("Sair", "Tem certeza que deseja encerrar o sistema?"):
            try:
                show_goodbye_screen(root, "Até Logo,\nBom descanso", duration_ms=1500)
            except Exception:
                pass

            def _finalizar_saida():
                try:
                    if login_win and login_win.winfo_exists():
                        login_win.destroy()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            root.after(1600, _finalizar_saida)
            return
        return

    root.protocol("WM_DELETE_WINDOW", on_close)

    menu_bar = tk.Menu(root)
    menu_sessao = tk.Menu(menu_bar, tearoff=0)
    # Tema (runtime)
    menu_tema = tk.Menu(menu_sessao, tearoff=0)
    tema_var = tk.StringVar(value="dark")
    def _on_theme_change():
        try:
            apply_theme(tema_var.get())
            _refresh_theme_widgets()
            _refresh_statusbar_theme()
            try:
                for t in (tree_cli, tree_upgrades, ag_tree, tree_cx, tree_m, tree_dev):
                # Estoque: sem zebra (somente cores por quantidade)
                    configure_zebra_tags(t, current_theme["name"])
                    apply_zebra(t)
            except Exception:
                pass
        except Exception:
            pass
    menu_tema.add_radiobutton(label="Escuro (Modern Dark)", variable=tema_var, value="dark", command=_on_theme_change)
    menu_tema.add_radiobutton(label="Claro (Windows 11)", variable=tema_var, value="light", command=_on_theme_change)
    menu_sessao.add_cascade(label="Tema", menu=menu_tema)
    def do_logout():
        if messagebox.askyesno(
            "Logout", "Deseja finalizar a sessão e voltar ao login?"
        ):
            closing_state["mode"] = "logout"
            on_close()
    def do_quit():
        closing_state["mode"] = None
        on_close()

    def alterar_senha():
        dlg = ChangePasswordDialog(root, username, must_change=False)
        root.wait_window(dlg)

    menu_sessao.add_command(label="Alterar senha…", command=alterar_senha)
    menu_sessao.add_command(label="Logout", accelerator="Ctrl+L", command=do_logout)
    menu_sessao.add_separator()
    menu_sessao.add_command(label="Sair", accelerator="Ctrl+Q", command=do_quit)
    menu_bar.add_cascade(label="Sessão", menu=menu_sessao)
    root.config(menu=menu_bar)
    root.bind_all("<Control-l>", lambda e: do_logout())
    root.bind_all("<Control-q>", lambda e: do_quit())
    root.bind_all("<Control-f>", lambda e: fechar_caixa())
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    default_font = ("Segoe UI", 10)
    heading_font = ("Segoe UI", 11, "bold")
    style.configure(".", font=default_font)
    style.configure("TLabel", font=default_font, padding=6)
    style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    style.configure("Treeview.Heading", font=heading_font)
    style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))

    # ====== MELHORIAS DE LAYOUT / TEMA (Modern Dark + toggle runtime) ======
    # Tema padrão: ESCURO (grafite) com destaques azul/verde
    current_theme = {"name": "dark"}
    palette = THEME_DARK

    def _apply_custom_styles(theme_name: str):
        nonlocal palette
        palette = THEME_DARK if theme_name == 'dark' else THEME_LIGHT

        # Fontes globais
        style.configure('.', font=BASE_FONT)
        style.configure('TLabel', font=BASE_FONT, padding=6)
        style.configure('TButton', font=BUTTON_FONT, padding=6)
        style.configure('TEntry', padding=4)
        style.configure('TCombobox', padding=4)

        # Notebook (abas) mais bonito
        style.configure('TNotebook.Tab', padding=[16, 10], font=("Segoe UI", 10, 'bold'))
        style.map('TNotebook.Tab',
                  foreground=[('selected', '#ffffff'), ('!selected', palette['muted'])],
                  background=[('selected', palette['accent']), ('!selected', palette['panel2'])])

        # Treeview (tabela) — header + seleção
        style.configure('Treeview.Heading', font=HEADING_FONT)
        try:
            style.configure('Treeview.Heading', background=palette['panel2'], foreground=palette['text'])
        except Exception:
            pass
        style.configure('Treeview', rowheight=28, font=BASE_FONT)
        style.configure('Treeview',
                        background=palette['bg'],
                        fieldbackground=palette['bg'],
                        foreground=palette['text'])
        style.map('Treeview',
                  foreground=[('selected', '#ffffff')],
                  background=[('selected', palette['accent'])])

    def apply_theme(theme_name: str):
        # sv-ttk (se disponível)
        if _HAS_SV_TTK and sv_ttk is not None:
            try:
                sv_ttk.set_theme(theme_name)
            except Exception:
                pass
        else:
            try:
                style.theme_use('clam')
            except Exception:
                pass
        current_theme['name'] = theme_name
        _apply_custom_styles(theme_name)

    # Aplica tema inicial
    apply_theme('dark')

    # Adicionando espaçamento padrão

    PADX = 8
    PADY = 6
    # ====== ESTILOS DE BOTÕES (cores e hover) ======
    # Paleta inspirada nas cores Tailwind para consistência visual
    style.configure("Success.TButton", foreground="white", background="#22c55e", padding=6)
    style.map("Success.TButton", background=[("active", "#16a34a"), ("pressed", "#15803d")])
    style.configure("Danger.TButton", foreground="white", background="#ef4444", padding=6)
    style.map("Danger.TButton", background=[("active", "#dc2626"), ("pressed", "#b91c1c")])
    style.configure("Secondary.TButton", foreground="white", background="#64748b", padding=6)
    style.map("Secondary.TButton", background=[("active", "#475569"), ("pressed", "#334155")])
    style.configure("Accent.TButton", foreground="white", background="#2563eb", padding=6)
    style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])
    # Botão já usado para fechar caixa
    style.configure("FecharCaixa.TButton", foreground="white", background="#2563eb", padding=6)
    style.map("FecharCaixa.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])
    style.configure("TNotebook.Tab", padding=[12, 8], font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", tabposition="n")
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    # ====== HEADER premium (logo + nome + versão + usuário + sair) ======
    header = tk.Frame(root, bg=palette['panel'], highlightbackground=palette['border'], highlightthickness=1)
    header.pack(fill='x', padx=12, pady=(10, 6))

    h_left = tk.Frame(header, bg=palette['panel'])
    h_left.pack(side='left', fill='x', expand=True)

    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((170, 52))
            log_img = ImageTk.PhotoImage(img)
            lbl_logo = tk.Label(h_left, image=log_img, bg=palette['panel'])
            lbl_logo.image = log_img
            lbl_logo.pack(side='left', padx=(10, 10), pady=8)
        except Exception:
            pass

    title_box = tk.Frame(h_left, bg=palette['panel'])
    title_box.pack(side='left', pady=8)
    tk.Label(title_box, text="BESIM COMPANY", bg=palette['panel'], fg=palette['text'],
             font=("Segoe UI", 14, "bold")).pack(anchor='w')
    tk.Label(title_box, text=f"Sistema Loja • v{get_local_version()}", bg=palette['panel'], fg=palette['muted'],
             font=("Segoe UI", 10)).pack(anchor='w')

    h_right = tk.Frame(header, bg=palette['panel'])
    h_right.pack(side='right', pady=8, padx=10)

    role = "admin" if is_admin(username) else "user"
    chip = tk.Frame(h_right, bg=palette['panel2'], highlightbackground=palette['border'], highlightthickness=1)
    chip.pack(side='right', padx=(8, 0))
    lbl_chip = tk.Label(chip, text=f"👤 {username} ({role})", bg=palette['panel2'], fg=palette['text'],
                        font=("Segoe UI", 10, "bold"))
    lbl_chip.pack(side='left', padx=10, pady=6)

    btn_sair = ttk.Button(h_right, text="Sair", style="Danger.TButton", command=do_logout)
    btn_sair.pack(side='right')

    _theme_widgets = {
        'header': header, 'h_left': h_left, 'h_right': h_right, 'title_box': title_box,
        'chip': chip, 'lbl_chip': lbl_chip
    }

    def _refresh_theme_widgets():
        try:
            pal = THEME_DARK if current_theme['name'] == 'dark' else THEME_LIGHT
            for key in ('header', 'h_left', 'h_right', 'title_box'):
                _theme_widgets[key].configure(bg=pal['panel'], highlightbackground=pal['border'])
            _theme_widgets['chip'].configure(bg=pal['panel2'], highlightbackground=pal['border'])
            _theme_widgets['lbl_chip'].configure(bg=pal['panel2'], fg=pal['text'])
        except Exception:
            pass

    # Notebook
    abas = ttk.Notebook(root)

    abas.pack(fill="both", expand=True, padx=12, pady=(8, 12))
    aba_estoque = ttk.Frame(abas, padding=10)
    aba_vendas = ttk.Frame(abas, padding=10)
    aba_clientes = ttk.Frame(abas, padding=10)
    aba_caixa = ttk.Frame(abas, padding=10)
    aba_manutencao = ttk.Frame(abas, padding=10)
    aba_devolucao = ttk.Frame(abas, padding=10)
    abas.add(aba_estoque, text="Estoque")
    abas.add(aba_vendas, text="Vendas")
    abas.add(aba_clientes, text="Clientes")
    abas.add(aba_caixa, text="Caixa")
    abas.add(aba_manutencao, text="Manutenção")
    abas.add(aba_devolucao, text="Devolução")

    aba_agendamento = ttk.Frame(abas, padding=10)
    abas.add(aba_agendamento, text="Agendamento")

    # Atualiza automaticamente a aba Vendas quando ela for selecionada
    def _on_tab_changed(event=None):
        try:
            if abas.select() == aba_vendas._w:
                carregar_vendas_dia()
        except Exception:
            pass

    abas.bind("<<NotebookTabChanged>>", _on_tab_changed)

    # ====== UPGRADE ======
    aba_upgrade = ttk.Frame(abas, padding=10)
    abas.add(aba_upgrade, text="Upgrade")
    f_u = ttk.Frame(aba_upgrade, padding=8)
    f_u.pack(fill="x", pady=6)
    ttk.Label(f_u, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_u = ttk.Entry(f_u)
    ent_cpf_u.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_u.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_u))
    ttk.Label(f_u, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_u = ttk.Entry(f_u)
    ent_nome_u.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_u, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_u = ttk.Entry(f_u)
    ent_tel_u.grid(row=0, column=5, padx=6, pady=4)
    ent_tel_u.bind("<KeyRelease>", lambda e: formatar_telefone(e, ent_tel_u))
    ttk.Label(f_u, text="Descrição").grid(row=1, column=0, sticky="w", padx=6, pady=6)
    ent_desc_u = ttk.Entry(f_u, width=70)
    ent_desc_u.grid(row=1, column=1, columnspan=4, pady=4, padx=6, sticky="we")
    ttk.Label(f_u, text="Valor").grid(row=1, column=5, sticky="w", padx=6, pady=6)
    ent_valor_u = ttk.Entry(f_u, width=18)
    ent_valor_u.grid(row=1, column=6, padx=6, pady=6)
    ent_valor_u.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_valor_u))
    ttk.Label(f_u, text="Pagamento").grid(row=2, column=5, sticky="w", padx=6, pady=6)
    ent_pg_u = ttk.Combobox(f_u, values=["PIX", "Cartão", "Dinheiro"], width=16)
    ent_pg_u.grid(row=2, column=6, padx=6, pady=6)
    def buscar_cliente_u():
        cpf = ent_cpf_u.get().strip()
        cursor.execute("SELECT nome, telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_u.delete(0, "end")
            ent_nome_u.insert(0, r[0])
            ent_tel_u.delete(0, "end")
            ent_tel_u.insert(0, r[1])
    ttk.Button(f_u, text="🔍 Buscar Cliente", style="Secondary.TButton", command=buscar_cliente_u).grid(row=0, column=6, padx=6)
    def finalizar_upgrade():
        try:
            cpf = ent_cpf_u.get().strip()
            cliente = ent_nome_u.get().strip() or "Sem Nome"
            telefone = ent_tel_u.get().strip()
            descricao = ent_desc_u.get().strip()
            valor_text = ent_valor_u.get().replace("R$", "").replace(",", ".").strip()
            if not descricao or not valor_text:
                messagebox.showwarning("Atenção", "Informe descrição e valor válido")
                return
            valor = float(valor_text)
            data = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            with conn:
                cursor.execute("INSERT INTO vendas(cliente,cpf,produto,quantidade,total,pagamento,data,hora) VALUES (?,?,?,?,?,?,?,?)", (cliente, cpf, descricao, 1, valor, (f"Upgrade - {ent_pg_u.get().strip()}" if ent_pg_u.get().strip() else "Upgrade"), data, hora))
                cursor.execute("INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)", (valor, data, hora, (f"Upgrade - {ent_pg_u.get().strip()}" if ent_pg_u.get().strip() else "Upgrade")))
                cursor.execute("INSERT OR IGNORE INTO clientes(cpf,nome,telefone) VALUES (?,?,?)", (cpf, cliente, telefone))
            try:
                gerar_cupom(cliente, descricao, 1, (ent_pg_u.get().strip() or "Upgrade"), valor)
            except Exception:
                pass
            messagebox.showinfo("Upgrade", f"Upgrade registrado! Total: R$ {valor:.2f}")
            # Atualiza também a lista de vendas do dia (upgrades geram venda)
            try:
                aba_vendas.after(30, carregar_vendas_dia)
            except Exception:
                pass
            carregar_upgrades()
            ent_cpf_u.delete(0, "end")
            ent_nome_u.delete(0, "end")
            ent_tel_u.delete(0, "end")
            ent_desc_u.delete(0, "end")
            ent_valor_u.delete(0, "end")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao registrar upgrade\n{ex}")
    ttk.Button(f_u, text="✓ Finalizar Upgrade", style="Success.TButton", command=finalizar_upgrade).grid(row=2, column=0, columnspan=2, pady=10, sticky="w", padx=6)
    # Histórico de Upgrades
    hist_u_frame = ttk.Frame(aba_upgrade, padding=(8, 0))
    hist_u_frame.pack(fill="both", expand=True)
    top_hist_u = ttk.Frame(hist_u_frame)
    top_hist_u.pack(fill="x", pady=(6, 6))
    ttk.Label(top_hist_u, text="Histórico de Upgrades", font=("Segoe UI", 11, "bold")).pack(side="left", padx=6)
    ttk.Button(top_hist_u, text="⟳ Atualizar", style="Secondary.TButton", command=lambda: carregar_upgrades()).pack(side="left", padx=6)
    tree_up_frame = ttk.Frame(hist_u_frame)
    tree_up_frame.pack(fill="both", expand=True)
    tree_upgrades = ttk.Treeview(tree_up_frame, columns=("Hora", "Cliente", "Descrição", "Pagamento", "Valor"), show="headings", height=10)
    configure_zebra_tags(tree_upgrades, current_theme["name"])
    for col, txt, anchor, width in [("Hora", "Hora", "center", 120), ("Cliente", "Cliente", "w", 200), ("Descrição", "Descrição", "w", 240), ("Pagamento", "Pagamento", "center", 140), ("Valor", "Valor", "e", 120)]:
        tree_upgrades.heading(col, text=txt)
        tree_upgrades.column(col, width=width, anchor=anchor)
    tree_upgrades.pack(side="left", fill="both", expand=True)
    scrollbar_upgrades = ttk.Scrollbar(tree_up_frame, orient="vertical", command=tree_upgrades.yview)
    tree_upgrades.configure(yscroll=scrollbar_upgrades.set)
    scrollbar_upgrades.pack(side="right", fill="y")
    # ====== FUNÇÃO PARA GERAR RELATÓRIO DE UPGRADES EM PDF ======
    def gerar_relatorio_upgrades_dia_pdf(data_str: str = None):
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        data_alvo = data_str or hoje
        pasta_rel = os.path.join(os.getcwd(), "relatorios")
        os.makedirs(pasta_rel, exist_ok=True)
        nome_arquivo = os.path.join(pasta_rel, f"relatorio_upgrades_{data_alvo.replace('/', '-')}.pdf")
        c = canvas.Canvas(nome_arquivo, pagesize=A4)
        logo_path_local = os.path.join(os.getcwd(), "logo.png")
        if os.path.exists(logo_path_local):
            try:
                c.drawImage(ImageReader(logo_path_local), 40, 780, width=140, height=40, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, 760, f"Relatório de Upgrades - {data_alvo}")
        c.setFont("Helvetica", 11)
        c.drawString(40, 742, "-" * 110)
        y = 720
        cursor.execute("SELECT hora, cliente, produto, pagamento, total FROM vendas WHERE data=? AND pagamento LIKE 'Upgrade%' ORDER BY hora DESC", (hoje,))
        linhas = cursor.fetchall()
        total_dia = 0.0
        if not linhas:
            c.drawString(40, y, "Nenhum upgrade registrado neste dia.")
            y -= 18
        else:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(40, y, "Hora")
            c.drawString(100, y, "Cliente")
            c.drawString(280, y, "Descrição")
            c.drawString(460, y, "Pagto")
            c.drawString(520, y, "Valor")
            y -= 16
            c.setFont("Helvetica", 10)
            for hora, cliente, produto, pagamento, total in linhas:
                total_dia += total or 0.0
                c.drawString(40, y, str(hora))
                c.drawString(100, y, str(cliente)[:24])
                c.drawString(280, y, str(produto)[:30])
                c.drawString(460, y, str(pagamento or "").replace("Upgrade - ", "")[:12])
                c.drawRightString(590, y, f"R$ {float(total):.2f}")
                y -= 16
                if y < 60:
                    c.showPage()
                    y = 780
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, f"Relatório de Upgrades - {data_alvo}")
                    y -= 20
                    c.setFont("Helvetica-Bold", 10)
                    c.drawString(40, y, "Hora")
                    c.drawString(100, y, "Cliente")
                    c.drawString(280, y, "Descrição")
                    c.drawString(460, y, "Pagto")
                    c.drawString(520, y, "Valor")
                    y -= 16
                    c.setFont("Helvetica", 10)
        y -= 24
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, f"Total de upgrades do dia: R$ {total_dia:.2f}")
        c.save()
        try:
            backup_pdf(nome_arquivo, "relatorios")
        except Exception:
            pass
        try:
            sistema = platform.system()
            if sistema == "Windows":
                os.startfile(nome_arquivo)
            elif sistema == "Darwin":
                os.system(f"open '{nome_arquivo}'")
            else:
                os.system(f"xdg-open '{nome_arquivo}'")
        except Exception:
            pass
        bring_app_to_front()
        return nome_arquivo
    # Adiciona botão na aba Upgrade
    ttk.Button(top_hist_u, text="📄 Exportar PDF", style="Accent.TButton", command=lambda: gerar_relatorio_upgrades_dia_pdf()).pack(side="left", padx=6)
    def carregar_upgrades():
        tree_upgrades.delete(*tree_upgrades.get_children())
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        cursor.execute("SELECT hora, cliente, produto, pagamento, total FROM vendas WHERE data=? AND pagamento LIKE 'Upgrade%' ORDER BY hora DESC", (hoje,))
        for hora, cliente, produto, pagamento, total in cursor.fetchall():
            tree_upgrades.insert("", "end", values=(hora, cliente, produto, (pagamento or "").replace("Upgrade - ", ""), f"R$ {total:.2f}"))
        apply_zebra(tree_upgrades)
    
    # ====== AGENDAMENTO (retirada de celulares) ======
    # UI: AGENDAMENTO
    ag_state = {"year": datetime.date.today().year, "month": datetime.date.today().month}

    # Cabeçalho com navegação
    ag_top = ttk.Frame(aba_agendamento, padding=8)
    ag_top.pack(fill="x")

    btn_prev = ttk.Button(ag_top, text="◀", width=4)
    btn_prev.pack(side="left", padx=(0, 6))

    lbl_mes = ttk.Label(ag_top, text="", font=("Segoe UI", 12, "bold"))
    lbl_mes.pack(side="left", padx=6)

    btn_next = ttk.Button(ag_top, text="▶", width=4)
    btn_next.pack(side="left", padx=6)

    def _go_today():
        ag_state["year"] = datetime.date.today().year
        ag_state["month"] = datetime.date.today().month
        refresh_agendamento_calendar()

    ttk.Button(ag_top, text="Hoje", style="Secondary.TButton", command=_go_today).pack(side="right", padx=6)

    # Grade do calendário
    ag_cal_frame = ttk.Frame(aba_agendamento, padding=(8, 4))
    ag_cal_frame.pack(fill="both", expand=True)

    # Linha com nomes dos dias (Seg a Dom)
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for i, d in enumerate(dias_semana):
        ttk.Label(ag_cal_frame, text=d, anchor="center", font=("Segoe UI", 10, "bold")).grid(row=0, column=i, sticky="nsew", padx=2, pady=(0, 4))
        ag_cal_frame.grid_columnconfigure(i, weight=1)

    # Container dos botões de dias
    ag_days_container = ttk.Frame(ag_cal_frame)
    ag_days_container.grid(row=1, column=0, columnspan=7, sticky="nsew")
    for i in range(7):
        ag_days_container.grid_columnconfigure(i, weight=1)

    # Lista (resumo) de agendamentos do mês
    ag_list_frame = ttk.Frame(aba_agendamento, padding=(8, 6))
    ag_list_frame.pack(fill="both", expand=False)

    ttk.Label(ag_list_frame, text="Agendamentos do mês", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=2, pady=(0, 6))

    ag_tree = ttk.Treeview(ag_list_frame, columns=("Data", "Responsável"), show="headings", height=6)
    configure_zebra_tags(ag_tree, current_theme["name"])
    ag_tree.heading("Data", text="Data")
    ag_tree.heading("Responsável", text="Responsável")
    ag_tree.column("Data", width=120, anchor="center", stretch=False)
    ag_tree.column("Responsável", width=900, anchor="w", stretch=True)
    ag_tree.pack(side="left", fill="both", expand=True)
    ag_scroll = ttk.Scrollbar(ag_list_frame, orient="vertical", command=ag_tree.yview)
    ag_tree.configure(yscroll=ag_scroll.set)
    ag_scroll.pack(side="right", fill="y")

    ag_scroll_x = ttk.Scrollbar(ag_list_frame, orient="horizontal", command=ag_tree.xview)
    ag_tree.configure(xscroll=ag_scroll_x.set)
    ag_scroll_x.pack(side="bottom", fill="x")

    def _ver_detalhes_agendamento(event=None):
        sel = ag_tree.selection()
        if not sel:
            return
        iso = sel[0]  # iid = data_iso
        try:
            cursor.execute("SELECT responsavel FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            r = cursor.fetchone()
            detalhes = (r[0] if r and r[0] else "(sem agendamentos)")
        except Exception as ex:
            detalhes = f"(erro ao carregar) {ex}"
        messagebox.showinfo(f"Agendamentos {_br_date_from_iso(iso)}", detalhes)

    ag_tree.bind("<Double-1>", _ver_detalhes_agendamento)
    def _mes_ano_pt(year: int, month: int) -> str:
        # Nomes em pt-BR
        nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        try:
            return f"{nomes[month-1]} {year}"
        except Exception:
            return f"{month:02d}/{year}"

    def _iso_date(year: int, month: int, day: int) -> str:
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _br_date_from_iso(iso: str) -> str:
        try:
            y, m, d = iso.split('-')
            return f"{d}/{m}/{y}"
        except Exception:
            return iso

    def _load_agendamentos_do_mes(year: int, month: int):
        # Retorna dict {dia: responsavel}
        resp = {}
        ym = f"{year:04d}-{month:02d}"
        try:
            cursor.execute("SELECT data_iso, responsavel FROM agendamentos_celulares WHERE substr(data_iso,1,7)=?", (ym,))
            for iso, r in cursor.fetchall():
                try:
                    dia = int(iso.split('-')[2])
                    resp[dia] = r or ""
                except Exception:
                    pass
        except Exception as ex:
            logging.error(f"Falha ao carregar agendamentos: {ex}", exc_info=True)
        return resp

    def _refresh_agendamento_lista(year: int, month: int):
        ag_tree.delete(*ag_tree.get_children())
        ym = f"{year:04d}-{month:02d}"
        try:
            cursor.execute("SELECT data_iso, responsavel FROM agendamentos_celulares WHERE substr(data_iso,1,7)=? ORDER BY data_iso", (ym,))
            for iso, r in cursor.fetchall():
                linhas = [l.strip() for l in (r or "").splitlines() if l.strip()]
                if not linhas:
                    resumo = ""
                elif len(linhas) == 1:
                    resumo = linhas[0]
                else:
                    resumo = f"{linhas[0]} (+{len(linhas)-1})"
                resumo = " ".join(resumo.split())
                MAX = 60
                if len(resumo) > MAX:
                    resumo = resumo[:MAX-3] + "..."
                ag_tree.insert("", "end", iid=str(iso), values=(_br_date_from_iso(iso), resumo))
            apply_zebra(ag_tree)
        except Exception as ex:
            logging.error(f"Falha ao atualizar lista de agendamentos: {ex}", exc_info=True)

    def _open_agendamento_dialog(day: int):
        year = ag_state["year"]
        month = ag_state["month"]
        iso = _iso_date(year, month, day)

        # Valor atual (se existir)
        atual = ""
        try:
            cursor.execute("SELECT responsavel FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            rr = cursor.fetchone()
            if rr and rr[0]:
                atual = rr[0]
        except Exception:
            pass

        # --- Janela multilinha (substitui simpledialog.askstring) ---
        win = tk.Toplevel(root)
        win.title("Agendamento - Retirada de Celulares")
        win.resizable(False, False)
        try:
            win.transient(root)
            win.grab_set()
        except Exception:
            pass

        # Centraliza
        try:
            win.update_idletasks()
            x = root.winfo_rootx() + (root.winfo_width() // 2) - 240
            y = root.winfo_rooty() + (root.winfo_height() // 2) - 170
            win.geometry(f"480x340+{x}+{y}")
        except Exception:
            win.geometry("480x340")

        info = (
            f"Pessoas que vão buscar em {_br_date_from_iso(iso)}:\n\n"
            "• Digite UM NOME por linha\n"
            "• Deixe em branco para remover o agendamento do dia\n"
        )
        ttk.Label(win, text=info, justify="left").pack(anchor="w", padx=12, pady=(12, 6))

        frm_text = ttk.Frame(win)
        frm_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        txt = tk.Text(frm_text, height=10, wrap="word")
        txt.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frm_text, orient="vertical", command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=sb.set)

        if atual:
            txt.insert("1.0", atual)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 12))

        def _salvar():
            texto_in = (txt.get("1.0", "end") or "").strip()
            nomes = [l.strip() for l in texto_in.splitlines() if l.strip()]
            texto = "\n".join(nomes)

            try:
                with conn:
                    if texto:
                        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        cursor.execute(
                            "INSERT INTO agendamentos_celulares(data_iso, responsavel, atualizado_em) VALUES (?,?,?) "
                            "ON CONFLICT(data_iso) DO UPDATE SET responsavel=excluded.responsavel, atualizado_em=excluded.atualizado_em",
                            (iso, texto, agora),
                        )
                    else:
                        cursor.execute("DELETE FROM agendamentos_celulares WHERE data_iso=?", (iso,))
            except Exception as ex:
                logging.error(f"Falha ao salvar agendamento: {ex}", exc_info=True)
                messagebox.showerror("Erro", f"Não foi possível salvar o agendamento.\n{ex}", parent=win)
                return

            try:
                win.destroy()
            except Exception:
                pass

            refresh_agendamento_calendar()

        def _cancelar():
            try:
                win.destroy()
            except Exception:
                pass

        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=_cancelar).pack(side="right", padx=6)
        ttk.Button(btns, text="Salvar", style="Success.TButton", command=_salvar).pack(side="right", padx=6)

        win.bind("<Escape>", lambda e: _cancelar())
        win.bind("<Control-Return>", lambda e: _salvar())

        win.bind("<Return>", lambda e: "break")
        # Enter cria nova linha no Text e não aciona atalhos globais
        txt.bind('<Return>', lambda e: (txt.insert('insert', '\n'), 'break')[1])
        txt.focus_set()
    def refresh_agendamento_calendar():
        year = ag_state["year"]
        month = ag_state["month"]

        lbl_mes.config(text=_mes_ano_pt(year, month))

        # Limpa botões existentes
        for w in ag_days_container.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Carrega agendamentos do mês
        ag_map = _load_agendamentos_do_mes(year, month)

        cal = calendar.Calendar(firstweekday=0)  # 0=Segunda
        weeks = cal.monthdayscalendar(year, month)

        # Grid 6 linhas no máximo
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    # célula vazia
                    ttk.Label(ag_days_container, text="").grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
                    continue

                resp = ag_map.get(day, "")
                # Texto do botão: dia + indicador
                if resp:
                    qtd = len([l for l in str(resp).splitlines() if l.strip()])
                    txt = f"{day}\n✓{qtd}"
                    style_btn = "Accent.TButton"
                else:
                    txt = str(day)
                    style_btn = "TButton"

                b = ttk.Button(ag_days_container, text=txt, command=lambda d=day: _open_agendamento_dialog(d), style=style_btn)
                b.grid(row=r, column=c, sticky="nsew", padx=2, pady=2, ipadx=2, ipady=6)

        _refresh_agendamento_lista(year, month)

    def _change_month(delta: int):
        y = ag_state["year"]
        m = ag_state["month"] + delta
        if m < 1:
            m = 12
            y -= 1
        elif m > 12:
            m = 1
            y += 1
        ag_state["year"] = y
        ag_state["month"] = m
        refresh_agendamento_calendar()

    btn_prev.config(command=lambda: _change_month(-1))
    btn_next.config(command=lambda: _change_month(1))

    # Carrega ao iniciar
    refresh_agendamento_calendar()

# ====== ESTOQUE ======
    est_top = ttk.Frame(aba_estoque)
    est_top.pack(fill="both", expand=True)
    tree_frame = ttk.Frame(est_top)
    tree_frame.pack(fill="both", expand=True, pady=(0, 8))
    tree = ttk.Treeview(
        tree_frame,
        columns=("Código", "Nome", "Tipo", "Preço", "Qtd"),
        show="headings",
        selectmode="browse",
    )
    configure_zebra_tags(tree, current_theme["name"])
    tree.heading("Código", text="Código")
    tree.heading("Nome", text="Nome")
    tree.heading("Tipo", text="Tipo")
    tree.heading("Preço", text="Preço")
    tree.heading("Qtd", text="Qtd")
    tree.column("Código", width=120, anchor="center")
    tree.column("Nome", width=420, anchor="w")
    tree.column("Tipo", width=140, anchor="center")
    tree.column("Preço", width=120, anchor="e")
    tree.column("Qtd", width=80, anchor="center")
    tree.pack(side="left", fill="both", expand=True)
    scrollbar_est = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscroll=scrollbar_est.set)
    scrollbar_est.pack(side="right", fill="y")


    # ===== Legenda de cores do Estoque =====

    leg_frame = ttk.Frame(aba_estoque)

    leg_frame.pack(fill="x", pady=(2, 8))


    ttk.Label(leg_frame, text="Legenda:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(6, 10))


    def _leg_chip(parent, text, bg, fg):

        chip = tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 9, "bold"), padx=10, pady=4)

        chip.pack(side="left", padx=4)

        return chip


    _leg_chip(leg_frame, "ZERADO (0)", "#7f1d1d", "white")

    _leg_chip(leg_frame, "BAIXO (≤ 5)", "tomato", "black")

    _leg_chip(leg_frame, "MÉDIO (6–7)", "orange", "black")

    _leg_chip(leg_frame, "OK (≥ 8)", "lightgreen", "black")


    ttk.Label(leg_frame, text="• Ordenado por menor estoque", font=("Segoe UI", 9)).pack(side="right", padx=8)
    f_est = ttk.Frame(aba_estoque, padding=(6, 8))
    f_est.pack(fill="x", pady=6)
    def make_labeled_entry(parent, label_text, width=15):
        frm = ttk.Frame(parent)
        lbl = ttk.Label(frm, text=label_text)
        ent = ttk.Entry(frm, width=width)
        lbl.pack(side="top", anchor="w")
        ent.pack(side="top", fill="x")
        return frm, ent
    frm_codigo, ent_codigo = make_labeled_entry(f_est, "Código", 15)
    frm_codigo.pack(side="left", padx=6)
    frm_nome, ent_nome = make_labeled_entry(f_est, "Nome", 25)
    frm_nome.pack(side="left", padx=6)
    frm_tipo = ttk.Frame(f_est)
    ttk.Label(frm_tipo, text="Tipo").pack(side="top", anchor="w")
    ent_tipo = ttk.Combobox(frm_tipo, values=["Acessório", "Manutenção"], width=16)
    ent_tipo.pack(side="top", fill="x")
    frm_tipo.pack(side="left", padx=6)
    frm_custo, ent_custo = make_labeled_entry(f_est, "Custo", 10)
    frm_custo.pack(side="left", padx=6)
    frm_preco, ent_preco = make_labeled_entry(f_est, "Preço", 10)
    frm_preco.pack(side="left", padx=6)
    frm_qtd, ent_qtd = make_labeled_entry(f_est, "Qtd", 6)
    frm_qtd.pack(side="left", padx=6)
    ent_custo.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_custo))
    ent_preco.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_preco))
    def listar_estoque():
        tree.delete(*tree.get_children())
        
        # ===== Cores do estoque (SEM zebra) =====
        # 0 = zerado (vermelho escuro)
        tree.tag_configure("zerado", background="#7f1d1d", foreground="white")  # vermelho escuro
        # <= 5 = baixo (vermelho)
        tree.tag_configure("baixo", background="tomato", foreground="black")
        # 6..7 = médio (laranja)
        tree.tag_configure("laranja", background="orange", foreground="black")
        # >= 8 = ok (verde)
        tree.tag_configure("verde", background="lightgreen", foreground="black")
        
        # ===== Ordenação: menor estoque primeiro =====
        # Observação: COALESCE garante que NULL vire 0
        cursor.execute("""
            SELECT codigo, nome, tipo, preco, COALESCE(estoque,0) as estoque
            FROM produtos
            ORDER BY COALESCE(estoque,0) ASC, nome ASC
        """)
        
        for codigo, nome, tipo, preco, qtd in cursor.fetchall():
            if qtd == 0:
                tag = "zerado"
            elif qtd <= 5:
                tag = "baixo"
            elif 6 <= qtd <= 7:
                tag = "laranja"
            else:
                tag = "verde"
        
            tree.insert("", "end", values=(codigo, nome, tipo, f"R$ {float(preco):.2f}", int(qtd)), tags=(tag,))
        
        # NÃO aplicar zebra no estoque
        # apply_zebra(tree)
    listar_estoque()
    btn_frame_est = ttk.Frame(aba_estoque)
    btn_frame_est.pack(fill="x", pady=(6, 0))
    def cadastrar_produto():
        try:
            codigo = ent_codigo.get().strip()
            nome = ent_nome.get().strip()
            tipo = ent_tipo.get().strip()
            custo = float(ent_custo.get().replace("R$", "").replace(",", "."))
            preco = float(ent_preco.get().replace("R$", "").replace(",", "."))
            qtd = int(ent_qtd.get() or 0)
            if not codigo or not nome or not tipo:
                messagebox.showwarning("Atenção", "Preencha todos os campos")
                return
            with conn:
                cursor.execute(
                    "INSERT INTO produtos (codigo,nome,tipo,custo,preco,estoque) VALUES (?,?,?,?,?,?)",
                    (codigo, nome, tipo, custo, preco, qtd),
                )
            listar_estoque()
            messagebox.showinfo("OK", "Produto cadastrado!")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Código já existe!")
        except ValueError:
            messagebox.showerror("Erro", "Digite números válidos")
    def excluir_produto():
        if not is_admin(username):
            messagebox.showerror(
                "Permissão negada", "Somente o administrador pode excluir produtos."
            )
            return
        item = tree.selection()
        if not item:
            messagebox.showwarning("Atenção", "Selecione um produto para excluir")
            return
        codigo = tree.item(item)["values"][0]
        if messagebox.askyesno("Excluir Produto", f"Deseja excluir o código {codigo}?"):
            with conn:
                cursor.execute("DELETE FROM produtos WHERE codigo=?", (codigo,))
            listar_estoque()
    def carregar_produto_selecionado():
        item = tree.selection()
        if not item:
            messagebox.showwarning("Atenção", "Selecione um produto na lista")
            return None
        vals = tree.item(item)["values"]
        ent_codigo.config(state="normal")
        ent_codigo.delete(0, "end")
        ent_nome.delete(0, "end")
        ent_custo.delete(0, "end")
        ent_preco.delete(0, "end")
        ent_qtd.delete(0, "end")
        ent_tipo.set("")
        ent_codigo.insert(0, vals[0])
        ent_nome.insert(0, vals[1])
        ent_tipo.set(vals[2])
        ent_preco.insert(0, str(vals[3]).replace("R$", "").strip())
        ent_qtd.insert(0, vals[4])
        ent_codigo.config(state="readonly")
        cursor.execute("SELECT custo FROM produtos WHERE codigo=?", (vals[0],))
        r = cursor.fetchone()
        if r is not None:
            try:
                ent_custo.insert(0, f"{float(r[0]):.2f}")
            except Exception:
                ent_custo.insert(0, str(r[0]))
        return vals[0]
    def salvar_edicao_produto():
        codigo = ent_codigo.get().strip()
        if not codigo:
            messagebox.showwarning(
                "Atenção",
                "Nenhum produto carregado para edição. Clique em 'Editar (carregar)' primeiro.",
            )
            return
        try:
            nome = ent_nome.get().strip()
            tipo = ent_tipo.get().strip()
            custo = float(ent_custo.get().replace("R$", "").replace(",", ".") or 0)
            preco = float(ent_preco.get().replace("R$", "").replace(",", ".") or 0)
            qtd = int(ent_qtd.get() or 0)
            if not nome or not tipo:
                messagebox.showwarning("Atenção", "Preencha nome e tipo")
                return
            if not messagebox.askyesno(
                "Salvar Edição", f"Deseja salvar as alterações do produto {codigo}?"
            ):
                return
            with conn:
                cursor.execute(
                    """
                    UPDATE produtos
                    SET nome=?, tipo=?, custo=?, preco=?, estoque=?
                    WHERE codigo=?
                    """,
                    (nome, tipo, custo, preco, qtd, codigo),
                )
            listar_estoque()
            messagebox.showinfo("Sucesso", "Produto atualizado com sucesso!")
            ent_codigo.config(state="normal")
            ent_codigo.delete(0, "end")
        except ValueError:
            messagebox.showerror("Erro", "Valores inválidos")
    tree.bind("<Double-1>", lambda e: carregar_produto_selecionado())
    btn_cad_prod = ttk.Button(
        btn_frame_est, text="Cadastrar", command=cadastrar_produto
    )
    btn_edit_load_prod = ttk.Button(
        btn_frame_est, text="Editar (carregar)", command=carregar_produto_selecionado
    )
    btn_save_edit_prod = ttk.Button(
        btn_frame_est, text="Salvar Edição", command=salvar_edicao_produto
    )
    btn_del_prod = ttk.Button(btn_frame_est, text="✖ Excluir", style="Danger.TButton", command=excluir_produto)
    btn_cad_prod.pack(side="left", padx=6)
    btn_edit_load_prod.pack(side="left", padx=6)
    btn_save_edit_prod.pack(side="left", padx=6)
    btn_del_prod.pack(side="left", padx=6)
    if not is_admin(username):
        btn_del_prod.state(["disabled"])
    # ====== CLIENTES ======
    # -- TABELA --
    frame_cli = ttk.Frame(aba_clientes)
    frame_cli.pack(fill="both", expand=True, pady=8)
    tree_cli = ttk.Treeview(
        frame_cli, columns=("CPF", "Nome", "Telefone"), show="headings"
    )
    configure_zebra_tags(tree_cli, current_theme["name"])
    tree_cli.heading("CPF", text="CPF")
    tree_cli.heading("Nome", text="Nome")
    tree_cli.heading("Telefone", text="Telefone")
    tree_cli.column("CPF", width=160, anchor="center")
    tree_cli.column("Nome", width=320)
    tree_cli.column("Telefone", width=160, anchor="center")
    tree_cli.pack(side="left", fill="both", expand=True)
    scroll_cli = ttk.Scrollbar(frame_cli, orient="vertical", command=tree_cli.yview)
    tree_cli.configure(yscroll=scroll_cli.set)
    scroll_cli.pack(side="right", fill="y")
    # -- FORMULÁRIO --
    form_cli = ttk.Frame(aba_clientes, padding=8)
    form_cli.pack(fill="x")
    ttk.Label(form_cli, text="CPF").grid(row=0, column=0, padx=6)
    e_cpf = ttk.Entry(form_cli)
    e_cpf.grid(row=0, column=1, padx=6)
    ttk.Label(form_cli, text="Nome").grid(row=0, column=2, padx=6)
    e_nome = ttk.Entry(form_cli, width=30)
    e_nome.grid(row=0, column=3, padx=6)
    ttk.Label(form_cli, text="Telefone").grid(row=0, column=4, padx=6)
    e_tel = ttk.Entry(form_cli)
    e_tel.grid(row=0, column=5, padx=6)
    e_cpf.bind("<KeyRelease>", lambda e: formatar_cpf(e, e_cpf))
    e_tel.bind("<KeyRelease>", lambda e: formatar_telefone(e, e_tel))
    # -- FUNÇÕES --
    def carregar_clientes():
        tree_cli.delete(*tree_cli.get_children())
        for cpf, nome, tel in cursor.execute(
            "SELECT cpf, nome, telefone FROM clientes ORDER BY nome"
        ):
            tree_cli.insert("", "end", values=(cpf, nome, tel))
    def salvar_cliente():
        cpf = e_cpf.get()
        nome = e_nome.get()
        tel = e_tel.get()
        if not cpf or not nome or not tel:
            messagebox.showwarning("Atenção", "Preencha todos os campos")
            return
        with conn:
            cursor.execute(
                "INSERT OR REPLACE INTO clientes (cpf, nome, telefone) VALUES (?,?,?)",
                (cpf, nome, tel),
            )
        carregar_clientes()
    # -- BUSCA POR NOME (filtro incremental) --
    filtro_frame = ttk.Frame(aba_clientes, padding=8)
    filtro_frame.pack(fill="x")
    ttk.Label(filtro_frame, text="Buscar por nome").pack(side="left", padx=6)
    e_busca_nome = ttk.Entry(filtro_frame, width=30)
    e_busca_nome.pack(side="left")
    def carregar_clientes_filtrado(query: str = ""):
        tree_cli.delete(*tree_cli.get_children())
        q = (query or "").strip()
        if q:
            cursor.execute(
                "SELECT cpf, nome, telefone FROM clientes WHERE nome LIKE ? ORDER BY nome",
                (f"%{q}%",),
            )
        else:
            cursor.execute("SELECT cpf, nome, telefone FROM clientes ORDER BY nome")
        for cpf, nome, tel in cursor.fetchall():
            tree_cli.insert("", "end", values=(cpf, nome, tel))
        apply_zebra(tree_cli)
    def _on_busca_nome(_evt=None):
        carregar_clientes_filtrado(e_busca_nome.get())
    e_busca_nome.bind("<KeyRelease>", _on_busca_nome)
    e_busca_nome.bind("<Return>", _on_busca_nome)
    def carregar_para_edicao(event=None):
        item = tree_cli.selection()
        if not item:
            return
        cpf, nome, tel = tree_cli.item(item)["values"]
        e_cpf.delete(0, "end")
        e_nome.delete(0, "end")
        e_tel.delete(0, "end")
        e_cpf.insert(0, cpf)
        e_nome.insert(0, nome)
        e_tel.insert(0, tel)
        e_cpf.config(state="readonly")
    tree_cli.bind("<Double-1>", carregar_para_edicao)
    ttk.Button(form_cli, text="Salvar Cliente", command=salvar_cliente).grid(
        row=1, column=1, pady=8
    )
    carregar_clientes()
    # ====== VENDAS ======
    f_v = ttk.Frame(aba_vendas, padding=8)
    f_v.pack(fill="x", pady=6)
    ttk.Label(f_v, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_v = ttk.Entry(f_v)
    ent_cpf_v.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_v.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_v))
    ent_cpf_v.bind("<FocusOut>", lambda e: formatar_cpf(e, ent_cpf_v))
    ttk.Label(f_v, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_v = ttk.Entry(f_v)
    ent_nome_v.grid(row=0, column=3, padx=6, pady=4)

    ttk.Label(f_v, text="E-mail").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_email_v = ttk.Entry(f_v, width=28)
    ent_email_v.grid(row=0, column=5, padx=6, pady=4)
    ttk.Label(f_v, text="Código Produto").grid(
        row=1, column=0, sticky="w", padx=6, pady=4
    )
    ent_cod_v = ttk.Entry(f_v)
    ent_cod_v.grid(row=1, column=1, padx=6, pady=4)
    ttk.Label(f_v, text="Produto").grid(row=1, column=2, sticky="w", padx=6, pady=4)
    ent_prod_v = ttk.Entry(f_v, state="readonly")
    ent_prod_v.grid(row=1, column=3, padx=6, pady=4)
    ttk.Label(f_v, text="Qtd").grid(row=2, column=0, sticky="w", padx=6, pady=4)
    ent_qtd_v = ttk.Entry(f_v)
    ent_qtd_v.grid(row=2, column=1, padx=6, pady=4)
    ttk.Label(f_v, text="Pagamento").grid(row=2, column=2, sticky="w", padx=6, pady=4)
    ent_pg_v = ttk.Combobox(f_v, values=["PIX", "Cartão", "Dinheiro"], width=14)
    ent_pg_v.grid(row=2, column=3, padx=6, pady=4)
    lbl_total_v = ttk.Label(f_v, text="Total: R$ 0.00", font=("Segoe UI", 12, "bold"))
    lbl_total_v.grid(row=3, column=0, columnspan=2, pady=10, sticky="w", padx=6)
    var_desc_5 = tk.IntVar()
    var_desc_10 = tk.IntVar()
    def atualizar_total(event=None):
        try:
            codigo = ent_cod_v.get().strip()
            qtd = int(ent_qtd_v.get() or 0)
            cursor.execute(
                "SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,)
            )
            r = cursor.fetchone()
            if r:
                nome_prod, preco, estoque = r
                total = preco * qtd
                if var_desc_5.get():
                    total *= 0.95
                elif var_desc_10.get():
                    total *= 0.90
                lbl_total_v.config(text=f"Total: R$ {total:.2f}")
            else:
                lbl_total_v.config(text="Total: R$ 0.00")
        except Exception:
            lbl_total_v.config(text="Total: R$ 0.00")
    ttk.Checkbutton(
        f_v,
        text="5%",
        variable=var_desc_5,
        command=lambda: [var_desc_10.set(0), atualizar_total()],
    ).grid(row=4, column=0, sticky="w", padx=6)
    ttk.Checkbutton(
        f_v,
        text="10%",
        variable=var_desc_10,
        command=lambda: [var_desc_5.set(0), atualizar_total()],
    ).grid(row=4, column=1, sticky="w", padx=6)

    var_enviar_email = tk.IntVar(value=1)
    chk_email = ttk.Checkbutton(
        f_v,
        text="Enviar cupom por e-mail",
        variable=var_enviar_email
    )
    chk_email.grid(row=4, column=2, columnspan=2, sticky="w", padx=6)
    add_tooltip(chk_email, "Se marcado, o sistema envia o cupom em PDF para o e-mail informado.")
    def buscar_cliente_v():
        cpf = ent_cpf_v.get().strip()
        cursor.execute("SELECT nome,telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_v.delete(0, "end")
            ent_nome_v.insert(0, r[0])
    ttk.Button(f_v, text="Buscar Cliente", command=buscar_cliente_v).grid(
        row=0, column=4, padx=6
    )
    def buscar_produto_v(event=None):
        codigo = ent_cod_v.get().strip()
        ent_prod_v.config(state="normal")
        ent_prod_v.delete(0, "end")
        cursor.execute("SELECT nome FROM produtos WHERE codigo=?", (codigo,))
        r = cursor.fetchone()
        if r:
            ent_prod_v.insert(0, r[0])
        else:
            ent_prod_v.insert(0, "Produto não encontrado")
        ent_prod_v.config(state="readonly")
        atualizar_total()
    ent_cod_v.bind("<KeyRelease>", buscar_produto_v)
    ent_cod_v.bind("<FocusOut>", buscar_produto_v)
    ent_qtd_v.bind("<KeyRelease>", atualizar_total)
    ent_qtd_v.bind("<FocusOut>", atualizar_total)
    def finalizar_venda():
        try:
            cpf = ent_cpf_v.get().strip()
            cliente = ent_nome_v.get().strip()
            codigo = ent_cod_v.get().strip()
            qtd = int(ent_qtd_v.get() or 0)
            pagamento = ent_pg_v.get().strip()
            if qtd <= 0:
                messagebox.showerror("Erro", "Quantidade inválida")
                return
            cursor.execute(
                "SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,)
            )
            r = cursor.fetchone()
            if not r:
                messagebox.showerror("Erro", "Produto não encontrado")
                return
            nome_prod, preco, estoque = r
            if qtd > estoque:
                messagebox.showerror("Erro", f"Apenas {estoque} unidades disponíveis")
                return
            total = preco * qtd
            if var_desc_5.get():
                total *= 0.95
            elif var_desc_10.get():
                total *= 0.90
            data = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            with conn:
                cursor.execute(
                    "INSERT INTO vendas(cliente,cpf,produto,quantidade,total,pagamento,data,hora) VALUES (?,?,?,?,?,?,?,?)",
                    (cliente, cpf, nome_prod, qtd, total, pagamento, data, hora),
                )
                cursor.execute(
                    "UPDATE produtos SET estoque=? WHERE codigo=?",
                    (estoque - qtd, codigo),
                )
                # >>> ATUALIZADO: grava hora na entrada do caixa (motivo NULL)
                cursor.execute(
                    "INSERT INTO caixa(valor,data,hora) VALUES (?,?,?)",
                    (total, data, hora),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO clientes(cpf,nome) VALUES (?,?)",
                    (cpf, cliente),
                )
            listar_estoque()
            # Atualiza a lista de vendas do dia automaticamente
            try:
                aba_vendas.after(30, carregar_vendas_dia)
            except Exception:
                pass

            # Gerar cupom e enviar por e-mail, se marcado
            try:
                caminho_pdf = gerar_cupom(cliente or "", nome_prod, qtd, pagamento or "", total)
                # valida o caminho do PDF antes de enviar
                if not caminho_pdf or not os.path.isfile(caminho_pdf):
                    try:
                        messagebox.showwarning("E-mail", "Cupom não foi gerado corretamente. O envio por e-mail foi pulado.")
                    except Exception:
                        pass
                    email_cliente = ""  # força pular envio
                # Captura e-mail e tenta enviar
                try:
                    email_cliente = ent_email_v.get().strip()
                except Exception:
                    email_cliente = ""
                if var_enviar_email.get() == 1 and email_cliente:
                    ok, detail = enviar_cupom_email(email_cliente, caminho_pdf)
                    if not ok:
                        try:
                            messagebox.showwarning("E-mail", f"Falha ao enviar e-mail:\n{detail}")
                        except Exception:
                            pass
            except Exception as e:
                logging.error(f"Falha ao gerar/enviar cupom: {e}", exc_info=True)
                try:
                    messagebox.showerror("Cupom/E-mail", "Erro: " + str(e))
                except Exception:
                    pass
        except Exception as ex:
            logging.error("Falha ao finalizar venda", exc_info=True)
            try:
                messagebox.showerror("Erro", f"Falha ao finalizar venda\n{ex}")
            except Exception:
                pass

    # --- Botões de ação da venda (recriados) ---
    acoes_venda = ttk.Frame(f_v)
    acoes_venda.grid(row=3, column=2, columnspan=4, padx=6, pady=8, sticky="e")

    btn_finalizar_venda = ttk.Button(
        acoes_venda,
        text="✓ Finalizar Venda",
        style="Success.TButton",
        command=finalizar_venda
    )
    btn_finalizar_venda.pack(side="left", padx=6)

    # (Opcional) Botão para limpar campos
    def limpar_venda():
        for w in (ent_cpf_v, ent_nome_v, ent_email_v, ent_cod_v, ent_prod_v, ent_qtd_v):
            try:
                w.config(state="normal")
                w.delete(0, "end")
            except Exception:
                pass
        ent_pg_v.set("")
        var_desc_5.set(0)
        var_desc_10.set(0)
        lbl_total_v.config(text="Total: R$ 0.00")
        try:
            ent_prod_v.config(state="readonly")
        except Exception:
            pass

    btn_limpar_venda = ttk.Button(
        acoes_venda,
        text="Limpar",
        style="Secondary.TButton",
        command=limpar_venda
    )
    btn_limpar_venda.pack(side="left", padx=6)

    # (Opcional) Atalho: Enter finaliza a venda
    # Atalho Enter (bind_all) removido para não interferir em campos multilinha (Agendamento)
    # Use Ctrl+Enter ou clique em '✓ Finalizar Venda'.
    hist_v_frame = ttk.Frame(aba_vendas, padding=(8, 0))
    hist_v_frame.pack(fill="both", expand=True)

    top_hist = ttk.Frame(hist_v_frame)
    top_hist.pack(fill="x", pady=(6, 6))

    lbl_hist = ttk.Label(top_hist, text="Vendas de Hoje", font=("Segoe UI", 11, "bold"))
    lbl_hist.pack(side="left", padx=6)

    ttk.Button(top_hist, text="Atualizar", command=lambda: carregar_vendas_dia()).pack(side="left", padx=6)
    ttk.Button(top_hist, text="📄 Exportar PDF", style="Accent.TButton", command=lambda: gerar_relatorio_vendas_dia_pdf()).pack(side="left", padx=6)

    # Botão: Excluir Venda (estorna do caixa)
    ttk.Button(top_hist, text="✖ Excluir Venda", style="Danger.TButton", command=lambda: excluir_venda()).pack(side="left", padx=6)

    combo_filtro_pg = ttk.Combobox(top_hist, values=["", "PIX", "Cartão", "Dinheiro"], width=16)
    combo_filtro_pg.pack(side="right", padx=6)
    combo_filtro_pg.set("")
    ttk.Label(top_hist, text="Filtrar por pagamento:").pack(side="right")

    tree_vendas_frame = ttk.Frame(hist_v_frame)
    tree_vendas_frame.pack(fill="both", expand=True)

    tree_vendas = ttk.Treeview(
        tree_vendas_frame,
        columns=("Hora", "Cliente", "Produto", "Qtd", "Pagamento", "Total"),
        show="headings",
        height=10,
    )

    for col, txt, anchor, width in [
        ("Hora", "Hora", "center", 120),
        ("Cliente", "Cliente", "w", 200),
        ("Produto", "Produto", "w", 240),
        ("Qtd", "Qtd", "center", 80),
        ("Pagamento", "Pagamento", "center", 120),
        ("Total", "Total", "e", 120),
    ]:
        tree_vendas.heading(col, text=txt)
        tree_vendas.column(col, width=width, anchor=anchor)

    tree_vendas.pack(side="left", fill="both", expand=True)
    scrollbar_vendas = ttk.Scrollbar(tree_vendas_frame, orient="vertical", command=tree_vendas.yview)
    tree_vendas.configure(yscroll=scrollbar_vendas.set)
    scrollbar_vendas.pack(side="right", fill="y")

    # >>> Ajuste de contraste nas tags de vendas
    tree_vendas.tag_configure("PIX", background="#e6ffed", foreground="black")
    tree_vendas.tag_configure("Cartão", background="#e6f0ff", foreground="black")
    tree_vendas.tag_configure("Dinheiro", background="#fff5e6", foreground="black")
    tree_vendas.tag_configure("default", background="white", foreground="black")

    def excluir_venda():
        """Exclui a venda selecionada na lista do dia e estorna o valor no caixa."""
        sel = tree_vendas.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma venda na lista para excluir.")
            return

        vid = sel[0]
        try:
            cursor.execute(
                "SELECT id, produto, quantidade, total, data, pagamento, cliente, hora FROM vendas WHERE id=?",
                (vid,),
            )
            r = cursor.fetchone()
            if not r:
                messagebox.showerror("Erro", "Venda não encontrada no banco de dados.")
                return

            _id, produto, qtd, total, data_v, pagamento, cliente_v, hora_v = r

            # Se o caixa do dia já foi fechado, bloquear para evitar inconsistência
            cursor.execute("SELECT total FROM fechamento_caixa WHERE data=?", (data_v,))
            if cursor.fetchone():
                messagebox.showwarning(
                    "Caixa já fechado",
                    f"O caixa do dia {data_v} já foi fechado.\n\nPara manter consistência, não é permitido excluir vendas após o fechamento.",
                )
                return

            msg = (
                "Deseja excluir esta venda?\n\n"
                f"ID: {_id}\n"
                f"Cliente: {cliente_v}\n"
                f"Produto: {produto}\n"
                f"Qtd: {qtd}\n"
                f"Pagamento: {pagamento}\n"
                f"Total: R$ {float(total):.2f}\n"
                f"Hora: {hora_v}"
            )

            if not messagebox.askyesno("Excluir Venda", msg):
                return

            hora_now = datetime.datetime.now().strftime("%H:%M:%S")

            with conn:
                # Remove a venda
                cursor.execute("DELETE FROM vendas WHERE id=?", (_id,))

                # Devolve estoque se for um produto cadastrado (por nome)
                try:
                    cursor.execute(
                        "UPDATE produtos SET estoque = COALESCE(estoque,0) + ? WHERE nome=?",
                        (int(qtd), str(produto)),
                    )
                except Exception:
                    pass

                # Estorna no caixa (lançamento negativo com motivo)
                try:
                    cursor.execute(
                        "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                        (-float(total), data_v, hora_now, f"Estorno - exclusão venda ID {_id}"),
                    )
                except Exception:
                    # Compatibilidade caso algum banco antigo não tenha motivo/hora
                    cursor.execute("INSERT INTO caixa(valor,data) VALUES (?,?)", (-float(total), data_v))

            # Atualiza telas
            try:
                listar_estoque()
            except Exception:
                pass
            try:
                carregar_vendas_dia()
            except Exception:
                pass
            try:
                atualizar_caixa()
            except Exception:
                pass

            messagebox.showinfo("OK", "Venda excluída e valor estornado do caixa.")

        except Exception as ex:
            logging.error("Falha ao excluir venda", exc_info=True)
            messagebox.showerror("Erro", f"Falha ao excluir venda\n{ex}")

    def carregar_vendas_dia():
        tree_vendas.delete(*tree_vendas.get_children())
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        filtro = (combo_filtro_pg.get() or "").strip()

        if filtro:
            cursor.execute(
                """
                SELECT id, hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=? AND pagamento=?
                ORDER BY hora DESC
                """,
                (hoje, filtro),
            )
        else:
            cursor.execute(
                """
                SELECT id, hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=?
                ORDER BY hora DESC
                """,
                (hoje,),
            )

        for vid, hora, cliente, produto, qtd, pagamento, total in cursor.fetchall():
            tag = pagamento if pagamento in ("PIX", "Cartão", "Dinheiro") else "default"
            tree_vendas.insert(
                "",
                "end",
                iid=str(vid),
                values=(hora, cliente, produto, qtd, pagamento, f"R$ {float(total):.2f}"),
                tags=(tag,),
            )

    combo_filtro_pg.bind("<<ComboboxSelected>>", lambda e: carregar_vendas_dia())

    # Carrega vendas ao abrir a aba
    try:
        carregar_vendas_dia()
    except Exception:
        pass

# ====== CAIXA ======
    f_cx = ttk.Frame(aba_caixa, padding=8)
    f_cx.pack(fill="both", expand=True)
    top_cx = ttk.Frame(f_cx)
    top_cx.pack(fill="x", pady=(0, 8))
    lbl_total_cx = ttk.Label(top_cx, text="", font=("Segoe UI", 12, "bold"))
    lbl_total_cx.pack(side="left", padx=6)
    lbl_data_hora = ttk.Label(top_cx, text="", font=("Segoe UI", 10))
    lbl_data_hora.pack(side="right", padx=6)
    caixa_ops = ttk.Frame(f_cx)
    caixa_ops.pack(fill="x", pady=6)
    frm_saida = ttk.Frame(caixa_ops)
    frm_saida.pack(side="left", padx=6)
    ttk.Label(frm_saida, text="Saída de Caixa").pack(anchor="w")
    # Valor
    ent_saida_cx = ttk.Entry(frm_saida, width=20)
    ent_saida_cx.pack(anchor="w", pady=4)
    ent_saida_cx.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_saida_cx))
    # >>> NOVO: Motivo da saída
    ttk.Label(frm_saida, text="Motivo").pack(anchor="w")
    ent_motivo_cx = ttk.Entry(frm_saida, width=30)
    ent_motivo_cx.pack(anchor="w", pady=4)
    add_tooltip(ent_motivo_cx, "Explique rapidamente o motivo desta saída (ex.: motoboy, compra de insumos, troco, etc.).")
    def registrar_saida_caixa():
        valor_text = ent_saida_cx.get().replace("R$", "").replace(",", ".").strip()
        motivo = ent_motivo_cx.get().strip()
        if not valor_text:
            messagebox.showwarning("Atenção", "Informe o valor da saída")
            return
        if not motivo:
            messagebox.showwarning("Atenção", "Informe o motivo da saída")
            return
        try:
            valor = float(valor_text)
            if valor <= 0:
                messagebox.showwarning(
                    "Atenção", "Informe um valor positivo para a saída"
                )
                return
            hoje = datetime.datetime.now().strftime("%d/%m/%Y")
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            with conn:
                cursor.execute(
                    "INSERT INTO caixa(valor,data,hora,motivo) VALUES (?,?,?,?)",
                    (-valor, hoje, hora, motivo),
                )
            ent_saida_cx.delete(0, "end")
            ent_motivo_cx.delete(0, "end")
            atualizar_caixa()
            messagebox.showinfo(
                "Saída", f"Saída de R$ {valor:.2f} registrada com sucesso"
            )
        except ValueError:
            messagebox.showerror("Erro", "Valor inválido")
    ttk.Button(caixa_ops, text="Registrar Saída", command=registrar_saida_caixa).pack(
        side="left", padx=6, pady=10
    )
    ttk.Button(caixa_ops, text="🔒 Fechar Caixa", style="FecharCaixa.TButton", command=lambda: fechar_caixa()).pack(side="left", padx=6, pady=10)
    ttk.Separator(f_cx, orient="horizontal").pack(fill="x", pady=6)
    tree_cx_frame = ttk.Frame(f_cx)
    tree_cx_frame.pack(fill="both", expand=True)
    tree_cx = ttk.Treeview(
        tree_cx_frame, columns=("Data", "Total"), show="headings", height=8
    )
    configure_zebra_tags(tree_cx, current_theme["name"])
    tree_cx.heading("Data", text="Data")
    tree_cx.heading("Total", text="Total Fechado")
    tree_cx.column("Data", width=200, anchor="center")
    tree_cx.column("Total", width=200, anchor="e")
    tree_cx.pack(side="left", fill="both", expand=True, padx=(0, 6))
    scrollbar_cx = ttk.Scrollbar(
        tree_cx_frame, orient="vertical", command=tree_cx.yview
    )
    tree_cx.configure(yscroll=scrollbar_cx.set)
    scrollbar_cx.pack(side="right", fill="y")
    def carregar_historico_cx():
        try:
            if not tree_cx.winfo_exists():
                return
            tree_cx.delete(*tree_cx.get_children())
            for row in cursor.execute(
                "SELECT data,total FROM fechamento_caixa ORDER BY data DESC"
            ):
                tree_cx.insert("", "end", values=(row[0], f"R$ {row[1]:.2f}"))
        except tk.TclError:
            return
        except Exception as ex:
            logging.error(f"Erro ao carregar histórico de caixa: {ex}", exc_info=True)
    def atualizar_caixa():
        agora = datetime.datetime.now()
        hoje = agora.strftime("%d/%m/%Y")
        cursor.execute("SELECT MAX(data) FROM caixa")
        ultima_data = cursor.fetchone()[0]
        if ultima_data and ultima_data != hoje:
            cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (ultima_data,))
            total_ultimo = cursor.fetchone()[0] or 0
            if total_ultimo != 0:
                with conn:
                    cursor.execute(
                        "INSERT OR REPLACE INTO fechamento_caixa (data,total) VALUES (?,?)",
                        (ultima_data, total_ultimo),
                    )
                cursor.execute("DELETE FROM caixa WHERE data=?", (ultima_data,))
                conn.commit()
        cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (hoje,))
        total_hoje = cursor.fetchone()[0] or 0
        lbl_total_cx.config(
            text=f"Total arrecadado hoje: R$ {total_hoje:.2f} \n Líquido: R$ {total_hoje:.2f}"
        )
        lbl_data_hora.config(text=f"Data e Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
        if aba_caixa.winfo_exists():
            aba_caixa.after(1000, atualizar_caixa)
    def fechar_caixa():
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (hoje,))
        total = cursor.fetchone()[0] or 0
        if total == 0:
            messagebox.showinfo("Fechar Caixa", "Nenhuma venda registrada hoje!")
            return
        if messagebox.askyesno(
            "Fechar Caixa", f"Total do dia: R$ {total:.2f}\nDeseja fechar o caixa?"
        ):
            # 1) Registra o fechamento do dia (não apaga os lançamentos ainda)
            with conn:
                cursor.execute(
                    "INSERT OR REPLACE INTO fechamento_caixa (data, total) VALUES (?, ?)",
                    (hoje, total),
                )
            # 2) Gera o PDF com VENDAS e SAÍDAS (os dados ainda estão na tabela 'caixa')
            pdf_path = gerar_relatorio_vendas_dia_pdf(data_str=hoje)
            # 3) Backups automáticos (banco, cupons, OS, relatórios)
            try:
                backup_banco()
                backup_bulk_dir(os.path.join(os.getcwd(), "cupons"), "cupons")
                backup_bulk_dir(os.path.join(os.getcwd(), "OS"), "OS")
                backup_bulk_dir(os.path.join(os.getcwd(), "relatorios"), "relatorios")
            except Exception:
                pass
            # 4) Somente agora apagamos os lançamentos do dia do caixa
            with conn:
                cursor.execute("DELETE FROM caixa WHERE data=?", (hoje,))
            messagebox.showinfo(
                "Fechar Caixa",
                f"Caixa do dia {hoje} fechado com sucesso!\nRelatório gerado:\n{pdf_path}",
            )
            carregar_historico_cx()
            atualizar_caixa()

    # --- Rodapé da aba Caixa: mensagem no canto inferior direito (vermelho e negrito) ---
    try:
        footer_cx = ttk.Frame(aba_caixa)
        footer_cx.pack(side="bottom", fill="x")
        ttk.Label(
            footer_cx,
            text="Obrigado meu Deus",
            style="Footer.TLabel",
            anchor="e",
            justify="right"
        ).pack(side="right", padx=8, pady=4)
    except Exception:
        pass
    # --- Fim do rodapé da aba Caixa ---

    # ====== MANUTENÇÃO ======
    f_m = ttk.Frame(aba_manutencao, padding=8)
    f_m.pack(fill="x", pady=6)
    ttk.Label(f_m, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_m = ttk.Entry(f_m)
    ent_cpf_m.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_m.bind("<KeyRelease>", partial(formatar_cpf, entry=ent_cpf_m))
    ttk.Label(f_m, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_m = ttk.Entry(f_m)
    ent_nome_m.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_m, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_m = ttk.Entry(f_m)
    ent_tel_m.grid(row=0, column=5, padx=6, pady=4)
    ttk.Label(f_m, text="Descrição").grid(row=1, column=0, sticky="w", padx=6, pady=6)
    ent_desc_m = ttk.Entry(f_m, width=70)
    ent_desc_m.grid(row=1, column=1, columnspan=5, pady=4, padx=6, sticky="we")
    ttk.Label(f_m, text="Valor").grid(row=1, column=6, sticky="w", padx=6, pady=6)
    ent_valor_m = ttk.Entry(f_m, width=18)
    ent_valor_m.grid(row=1, column=7, padx=6, pady=6)
    ent_valor_m.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_valor_m))
    tree_m_frame = ttk.Frame(aba_manutencao)
    tree_m_frame.pack(fill="both", expand=True, pady=8)
    tree_m = ttk.Treeview(
        tree_m_frame,
        columns=(
            "OS",
            "Nome",
            "CPF",
            "Telefone",
            "Descrição",
            "Data",
            "Valor",
            "Aprovado",
        ),
        show="headings",
    )
    configure_zebra_tags(tree_m, current_theme["name"])
    for c in tree_m["columns"]:
        tree_m.heading(c, text=c)
    tree_m.column("OS", width=80, anchor="center")
    tree_m.column("Nome", width=220, anchor="w")
    tree_m.column("CPF", width=140, anchor="center")
    tree_m.column("Telefone", width=140, anchor="center")
    tree_m.column("Descrição", width=360, anchor="w")
    tree_m.column("Data", width=120, anchor="center")
    tree_m.column("Valor", width=120, anchor="e")
    tree_m.column("Aprovado", width=100, anchor="center")
    tree_m.pack(side="left", fill="both", expand=True)
    scrollbar_m = ttk.Scrollbar(tree_m_frame, orient="vertical", command=tree_m.yview)
    tree_m.configure(yscroll=scrollbar_m.set)
    scrollbar_m.pack(side="right", fill="y")
    def carregar_manutencao():
        tree_m.delete(*tree_m.get_children())
        for row in cursor.execute(
            "SELECT os, nome, cpf, telefone, descricao, data, COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao ORDER BY os DESC"
        ):
            aprovado_text = "Sim" if row[7] == 1 else "Não"
            tree_m.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    f"R$ {row[6]:.2f}",
                    aprovado_text,
                ),
            )
    carregar_manutencao()
    def buscar_cliente_m(event=None):
        try:
            cpf = ent_cpf_m.get().strip()
            cursor.execute("SELECT nome, telefone FROM clientes WHERE cpf=?", (cpf,))
            r = cursor.fetchone()
            if r:
                ent_nome_m.delete(0, "end")
                ent_nome_m.insert(0, str(r[0] or ""))
                ent_tel_m.delete(0, "end")
                ent_tel_m.insert(0, str(r[1] or ""))
        except Exception as ex:
            logging.error(f"Falha ao buscar cliente (OS): {ex}", exc_info=True)
    ttk.Button(f_m, text="Buscar Cliente", command=buscar_cliente_m).grid(
        row=0, column=6, padx=6
    )
    def cadastrar_manutencao():
        cpf = ent_cpf_m.get().strip()
        nome = ent_nome_m.get().strip()
        if not nome:
            nome = "Sem Nome"
        telefone = ent_tel_m.get().strip()
        desc = ent_desc_m.get().strip()
        valor_text = ent_valor_m.get().replace("R$", "").replace(",", ".").strip()
        if not desc or not valor_text:
            messagebox.showwarning("Atenção", "Informe descrição e um valor válido")
            return
        try:
            valor = float(valor_text)
        except ValueError:
            messagebox.showerror("Erro", "Valor inválido")
            return
        data = datetime.datetime.now().strftime("%d/%m/%Y")
        with conn:
            cursor.execute(
                "INSERT INTO manutencao(cpf,nome,telefone,descricao,data,valor) VALUES (?,?,?,?,?,?)",
                (cpf, nome, telefone, desc, data, valor),
            )
        os_num = cursor.lastrowid
        gerar_os_pdf(os_num, nome, cpf, telefone, desc, valor)
        carregar_manutencao()
        ent_cpf_m.delete(0, "end")
        ent_nome_m.config(state="normal")
        ent_nome_m.delete(0, "end")
        ent_nome_m.config(state="normal")
        ent_tel_m.config(state="normal")
        ent_tel_m.delete(0, "end")
        ent_tel_m.config(state="normal")
        ent_desc_m.delete(0, "end")
        ent_valor_m.delete(0, "end")
        messagebox.showinfo("OS", "Ordem de serviço registrada!")
    btn_reg_manut = ttk.Button(
        f_m, text="Registrar Manutenção", command=cadastrar_manutencao
    )
    btn_reg_manut.grid(row=2, column=0, columnspan=2, pady=8)
    def excluir_manutencao():
        if not is_admin(username):
            messagebox.showerror(
                "Permissão negada", "Somente o administrador pode excluir manutenções."
            )
            return
        selected = tree_m.selection()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma OS para excluir.")
            return
        item_id = selected[0]
        os_num = tree_m.item(item_id)["values"][0]
        if messagebox.askyesno("Excluir OS", f"Deseja excluir a OS {os_num}?"):
            with conn:
                cursor.execute("DELETE FROM manutencao WHERE os=?", (os_num,))
            carregar_manutencao()
    btn_excluir_manut = ttk.Button(
        f_m, text="Excluir Manutenção", command=excluir_manutencao
    )
    btn_excluir_manut.grid(row=2, column=2, columnspan=2, pady=8)
    if not is_admin(username):
        btn_excluir_manut.state(["disabled"])
    def aprovar_manutencao():
        selected = tree_m.selection()
        if not selected:
            messagebox.showwarning(
                "Atenção", "Selecione a OS que será aprovada na lista."
            )
            return
        item_id = selected[0]
        os_num = tree_m.item(item_id)["values"][0]
        cursor.execute(
            "SELECT COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao WHERE os=?",
            (os_num,), # sempre tupla
        )
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "OS não encontrada.")
            return
        valor, aprovado = r
        if aprovado == 1:
            messagebox.showinfo("Info", f"A OS {os_num} já foi aprovada.")
            return
        if valor <= 0:
            messagebox.showwarning("Atenção", "Valor inválido para aprovar.")
            return
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with conn:
                # >>> ATUALIZADO: grava hora na entrada do caixa (motivo NULL)
                cursor.execute(
                    "INSERT INTO caixa(valor,data,hora) VALUES (?,?,?)",
                    (valor, hoje, hora),
                )
                cursor.execute(
                    "UPDATE manutencao SET aprovado=1 WHERE os=?", (os_num,)
                ) # vírgula aqui
            carregar_manutencao()
            atualizar_caixa()
            messagebox.showinfo(
                "Aprovado",
                f"OS {os_num} aprovada. R$ {valor:.2f} adicionados ao caixa.",
            )
        except Exception as ex:
            logging.error("Falha ao aprovar manutenção", exc_info=True)
            messagebox.showerror("Erro", f"Falha ao aprovar manutenção:\n{ex}")
    # Cria o botão APÓS definir a função
    btn_aprovar_manut = ttk.Button(
        f_m, text="Manutenção Aprovada", command=aprovar_manutencao
    )
    btn_aprovar_manut.grid(row=2, column=4, columnspan=2, pady=8)
    # ====== DEVOLUÇÃO ======
    f_d = ttk.Frame(aba_devolucao, padding=8)
    f_d.pack(fill="x", pady=6)
    ttk.Label(f_d, text="Quem devolve").grid(
        row=0, column=0, sticky="w", padx=6, pady=4
    )
    ent_nome_dev = ttk.Entry(f_d, width=30)
    ent_nome_dev.grid(row=0, column=1, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Qual a devolução").grid(
        row=0, column=2, sticky="w", padx=6, pady=4
    )
    ent_devolucao = ttk.Entry(f_d, width=40)
    ent_devolucao.grid(row=0, column=3, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Motivo da devolução").grid(
        row=1, column=0, sticky="w", padx=6, pady=4
    )
    ent_motivo_dev = ttk.Entry(f_d, width=80)
    ent_motivo_dev.grid(row=1, column=1, columnspan=3, padx=6, pady=4, sticky="we")
    hist_d_frame = ttk.Frame(aba_devolucao, padding=(8, 0))
    hist_d_frame.pack(fill="both", expand=True)
    top_hist_d = ttk.Frame(hist_d_frame)
    top_hist_d.pack(fill="x", pady=(6, 6))
    ttk.Label(
        top_hist_d, text="Histórico de Devoluções", font=("Segoe UI", 11, "bold")
    ).pack(side="left", padx=6)
    ttk.Button(
        top_hist_d, text="Atualizar", command=lambda: carregar_devolucoes()
    ).pack(side="left", padx=6)
    tree_dev_frame = ttk.Frame(hist_d_frame)
    tree_dev_frame.pack(fill="both", expand=True)
    tree_dev = ttk.Treeview(
        tree_dev_frame,
        columns=("Data", "Hora", "Nome", "Item", "Motivo"),
        show="headings",
        height=10,
    )
    configure_zebra_tags(tree_dev, current_theme["name"])
    for col, txt, anchor, width in [
        ("Data", "Data", "center", 120),
        ("Hora", "Hora", "center", 100),
        ("Nome", "Nome", "w", 180),
        ("Item", "Item", "w", 240),
        ("Motivo", "Motivo", "w", 320),
    ]:
        tree_dev.heading(col, text=txt)
        tree_dev.column(col, width=width, anchor=anchor)
    tree_dev.pack(side="left", fill="both", expand=True)
    scrollbar_dev = ttk.Scrollbar(
        tree_dev_frame, orient="vertical", command=tree_dev.yview
    )
    tree_dev.configure(yscroll=scrollbar_dev.set)
    scrollbar_dev.pack(side="right", fill="y")
    def carregar_devolucoes():
        tree_dev.delete(*tree_dev.get_children())
        cursor.execute(
            """
            SELECT data, hora, nome, item, motivo
            FROM devolucoes
            ORDER BY date(substr(data,7,4)
                         || '-'
                         || substr(data,4,2)
                         || '-'
                         || substr(data,1,2)) DESC, hora DESC
            """
        )
        for data, hora, nome, item, motivo in cursor.fetchall():
            tree_dev.insert("", "end", values=(data, hora, nome, item, motivo))
        apply_zebra(tree_dev)
    def registrar_devolucao():
        nome = ent_nome_dev.get().strip()
        item = ent_devolucao.get().strip()
        motivo = ent_motivo_dev.get().strip()
        if not nome or not item or not motivo:
            messagebox.showwarning(
                "Atenção", "Preencha nome, item e motivo da devolução"
            )
            return
        data = datetime.datetime.now().strftime("%d/%m/%Y")
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with conn:
                cursor.execute(
                    "INSERT INTO devolucoes(item,motivo,nome,data,hora) VALUES (?,?,?,?,?)",
                    (item, motivo, nome, data, hora),
                )
            messagebox.showinfo("Devolução", "Devolução registrada com sucesso!")
            ent_nome_dev.delete(0, "end")
            ent_devolucao.delete(0, "end")
            ent_motivo_dev.delete(0, "end")
            carregar_devolucoes()
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao registrar devolução\n{ex}")
    ttk.Button(f_d, text="Registrar Devolução", command=registrar_devolucao).grid(
        row=2, column=0, pady=10, sticky="w", padx=6
    )
    carregar_devolucoes()
    # ---- Funções de UI: toast e agendador de backup ----
    def _show_toast_backup(text: str, level: str = 'info'):
        try:
            show_toast(root, text, level=level, duration_ms=3500, anchor='top-right', max_stack=4)
        except Exception:
            pass
            root._toast_frame = tk.Frame(root, bg=bg, highlightthickness=0)
            lbl = tk.Label(
                root._toast_frame,
                text=text,
                bg=bg,
                fg=fg,
                font=("Segoe UI", 10, "bold"),
            )
            lbl.pack(padx=10, pady=6)
            root._toast_frame.place(relx=0.5, rely=0.02, anchor="n")
            root.after(
                5000,
                lambda: (
                    root._toast_frame.destroy()
                    if root._toast_frame.winfo_exists()
                    else None
                ),
            )
        except Exception:
            pass
    def _backup_timer_tick():
        """Executa os backups e reprograma o próximo disparo (30 min)."""
        try:
            backup_banco()
            backup_bulk_dir(os.path.join(os.getcwd(), "cupons"), "cupons")
            backup_bulk_dir(os.path.join(os.getcwd(), "OS"), "OS")
            backup_bulk_dir(os.path.join(os.getcwd(), "relatorios"), "relatorios")
            try:
                ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                lbl_status_backup.config(text=f"Backup automático concluído: {ts}")
                _show_toast_backup("Backup automático concluído", "ok")
            except Exception:
                pass
        except Exception:
            pass
        finally:
            root.after(1_800_000, _backup_timer_tick)
    # Disparo inicial: 5 min; depois agenda de 30 min
    root.after(300_000, _backup_timer_tick)
    # Atualiza os totais do caixa ao abrir a janela
    try:
        atualizar_caixa()
    except Exception:
        pass

    # ====== STATUS BAR (versão | backup | usuário | data/hora) ======
    statusbar = tk.Frame(root, bg=palette['panel'], highlightbackground=palette['border'], highlightthickness=1)
    statusbar.pack(side='bottom', fill='x')

    lbl_status_left = tk.Label(statusbar, text=f"v{get_local_version()}", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_left.pack(side='left', padx=10, pady=6)

    lbl_status_backup = tk.Label(statusbar, text="Backup: aguardando...", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_backup.pack(side='left', padx=10, pady=6)

    lbl_status_user = tk.Label(statusbar, text=f"Usuário: {username}", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_user.pack(side='right', padx=10, pady=6)

    lbl_status_clock = tk.Label(statusbar, text="", bg=palette['panel'], fg=palette['muted'], font=("Segoe UI", 9))
    lbl_status_clock.pack(side='right', padx=10, pady=6)

    def _tick_clock():
        try:
            now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            lbl_status_clock.config(text=now)
        except Exception:
            pass
        root.after(1000, _tick_clock)

    _tick_clock()

    def _refresh_statusbar_theme():
        try:
            pal = THEME_DARK if current_theme['name'] == 'dark' else THEME_LIGHT
            statusbar.configure(bg=pal['panel'], highlightbackground=pal['border'])
            for w in (lbl_status_left, lbl_status_backup, lbl_status_user, lbl_status_clock):
                w.configure(bg=pal['panel'], fg=pal['muted'])
        except Exception:
            pass
# ================= TELA DE LOGIN =================

def abrir_login():
    login_win = tk.Tk()
    login_win.title("Login - BESIM COMPANY")
    login_win.geometry("520x360")
    login_win.minsize(520, 360)
    login_win.resizable(False, False)

    setup_global_exception_handlers(login_win)
    _bind_fullscreen_shortcuts(login_win)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Dark fixo
    pal = THEME_DARK

    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _draw_vertical_gradient(canvas, w, h, top="#0b1220", bottom="#111827", steps=220):
        c1 = _hex_to_rgb(top)
        c2 = _hex_to_rgb(bottom)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            y1 = int(h * (i / steps))
            y2 = int(h * ((i + 1) / steps))
            canvas.create_rectangle(0, y1, w, y2, outline="", fill=_rgb_to_hex((r, g, b)))

    bg = tk.Canvas(login_win, highlightthickness=0, bd=0)
    bg.pack(fill="both", expand=True)

    login_win.update_idletasks()
    _draw_vertical_gradient(bg, 520, 360, top="#0b1220", bottom="#111827")

    # Blobs (bolas) — azul, vermelho e cinza (reposicionadas para não tampar o logo)
    bg.create_oval(-140, -120, 180, 220, fill=pal["accent"], outline="")   # azul
    bg.create_oval(360, -140, 700, 220, fill=pal["danger"], outline="")    # vermelho
    bg.create_oval(360, 210, 740, 610, fill=pal["border"], outline="")     # cinza

    # Camada escura para suavizar o fundo (não afeta o card porque ele é desenhado depois)
    bg.create_rectangle(0, 0, 520, 360, fill="#0b1220", outline="", stipple="gray25")

    # Card central
    card_x1, card_y1, card_x2, card_y2 = 110, 62, 410, 298
    bg.create_rectangle(card_x1 + 6, card_y1 + 8, card_x2 + 6, card_y2 + 8,
                        fill="#000000", outline="", stipple="gray50")
    bg.create_rectangle(card_x1, card_y1, card_x2, card_y2,
                        fill=pal["panel"], outline=pal["border"], width=2)
    bg.create_rectangle(card_x1, card_y1, card_x2, card_y1 + 58,
                        fill=pal["panel2"], outline="", width=0)

    # Logo + glow atrás (garantido atrás do logo)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    cx, cy = (card_x1 + card_x2)//2, card_y1 + 30

    # Glow (desenhado antes do logo)
    bg.create_oval(cx-92, cy-32, cx+92, cy+32, fill=pal["accent"], outline="")
    bg.create_oval(cx-74, cy-26, cx+74, cy+26, fill=pal["danger"], outline="")
    bg.create_rectangle(cx-118, cy-40, cx+118, cy+40, fill="#000000", outline="", stipple="gray50")

    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((160, 52))
            logo_img = ImageTk.PhotoImage(img)
            bg.create_image(cx, cy, image=logo_img)
            bg.logo_img = logo_img
        except Exception:
            bg.create_text(cx, cy, text="BESIM COMPANY", fill=pal["text"], font=("Segoe UI", 14, "bold"))
    else:
        bg.create_text(cx, cy, text="BESIM COMPANY", fill=pal["text"], font=("Segoe UI", 14, "bold"))

    bg.create_text((card_x1 + card_x2)//2, card_y1 + 72,
                   text="Acesse sua conta para continuar",
                   fill=pal["muted"], font=("Segoe UI", 9))

    frm = tk.Frame(login_win, bg=pal["panel"])
    bg.create_window((card_x1 + card_x2)//2, (card_y1 + card_y2)//2 + 18, window=frm, width=280, height=210)

    style.configure("Accent.TButton", foreground="white", background=pal["accent"], padding=8,
                    font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])

    style.configure("Ghost.TButton", foreground=pal["text"], background=pal["panel2"], padding=8,
                    font=("Segoe UI", 10, "bold"))
    style.map("Ghost.TButton", background=[("active", pal["border"]), ("pressed", pal["panel2"])])

    style.configure("TEntry", padding=6)

    remember_path = os.path.join(os.getcwd(), "remember_user.txt")

    def _load_remembered_user():
        try:
            if os.path.isfile(remember_path):
                with open(remember_path, "r", encoding="utf-8") as f:
                    return (f.read() or "").strip()
        except Exception:
            pass
        return ""

    def _save_remembered_user(username: str):
        try:
            with open(remember_path, "w", encoding="utf-8") as f:
                f.write((username or "").strip())
        except Exception:
            pass

    def _clear_remembered_user():
        try:
            if os.path.isfile(remember_path):
                os.remove(remember_path)
        except Exception:
            pass

    tk.Label(frm, text="Usuário", bg=pal["panel"], fg=pal["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
    ent_user = ttk.Entry(frm)
    ent_user.pack(fill="x", pady=(0, 8))

    tk.Label(frm, text="Senha", bg=pal["panel"], fg=pal["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 2))
    pass_row = tk.Frame(frm, bg=pal["panel"])
    pass_row.pack(fill="x", pady=(0, 4))

    ent_pass = ttk.Entry(pass_row, show="*")
    ent_pass.pack(side="left", fill="x", expand=True)

    show_var = tk.IntVar(value=0)

    def _toggle_pass():
        ent_pass.config(show="" if show_var.get() else "*")

    ttk.Checkbutton(pass_row, text="👁️", variable=show_var, command=_toggle_pass).pack(side="left", padx=(6, 0))

    remember_var = tk.IntVar(value=1)
    remember_row = tk.Frame(frm, bg=pal["panel"])
    remember_row.pack(fill="x", pady=(6, 8))
    ttk.Checkbutton(remember_row, text="Lembrar usuário", variable=remember_var).pack(side="left")

    login_win.ent_user = ent_user
    login_win.ent_pass = ent_pass

    remembered = _load_remembered_user()
    if remembered:
        ent_user.insert(0, remembered)
        ent_pass.focus_set()
    else:
        ent_user.focus_set()

    def tentar_login():
        user = (ent_user.get() or "").strip()
        pw = (ent_pass.get() or "").strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha")
            return

        cursor.execute("SELECT password_hash FROM users WHERE username=?", (user,))
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "Usuário não encontrado")
            return

        if hash_password(pw) == r[0]:
            if remember_var.get() == 1:
                _save_remembered_user(user)
            else:
                _clear_remembered_user()

            must_change = False
            try:
                if is_admin(user) and days_since_last_change(user) >= 30:
                    must_change = True
            except Exception:
                must_change = True

            if must_change:
                dlg = ChangePasswordDialog(login_win, user, must_change=True)
                login_win.wait_window(dlg)
                if not dlg.result:
                    return

            login_win.withdraw()
            try:
                abrir_sistema_com_logo(user, login_win)
            except Exception as ex:
                messagebox.showerror("Erro fatal", f"Falha ao abrir a janela principal\n\n{ex}")
                login_win.deiconify()
        else:
            messagebox.showerror("Erro", "Senha incorreta")

    def criar_usuario():
        user = (ent_user.get() or "").strip()
        pw = (ent_pass.get() or "").strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha para criar")
            return
        try:
            today = datetime.datetime.now().strftime("%d/%m/%Y")
            with conn:
                cursor.execute("PRAGMA table_info(users)")
                cols = [c[1] for c in cursor.fetchall()]
                if 'password_last_changed' in cols:
                    cursor.execute(
                        "INSERT INTO users(username, password_hash, is_admin, password_last_changed) VALUES (?,?,0,?)",
                        (user, hash_password(pw), today)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO users(username, password_hash, is_admin) VALUES (?,?,0)",
                        (user, hash_password(pw))
                    )
                cursor.execute(
                    "INSERT OR IGNORE INTO user_password_history (username, password_hash, changed_at) VALUES (?,?,?)",
                    (user, hash_password(pw), today)
                )
            messagebox.showinfo("OK", "Usuário criado com sucesso")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Usuário já existe")

    btns = tk.Frame(frm, bg=pal["panel"])
    btns.pack(fill="x", pady=(6, 0))
    ttk.Button(btns, text="Entrar", style="Accent.TButton", command=tentar_login).pack(side="left", expand=True, fill="x", padx=(0, 6))
    ttk.Button(btns, text="Criar Usuário", style="Ghost.TButton", command=criar_usuario).pack(side="left", expand=True, fill="x")

    footer_text = f"Developed by André Mariano (v{get_local_version()})  •  Beta Test"
    bg.create_text(260, 334, text=footer_text, fill="#9ca3af", font=("Segoe UI", 9))

    login_win.bind("<Return>", lambda e: tentar_login())

    def on_close_login():
        if messagebox.askyesno("Sair", "Deseja encerrar o sistema?"):
            try:
                show_goodbye_screen(login_win, "Até Logo,\nBom descanso", duration_ms=1500)
            except Exception:
                pass

            def _finalizar_saida():
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    login_win.destroy()
                except Exception:
                    pass

            login_win.after(1600, _finalizar_saida)
            return
        return

    login_win.protocol("WM_DELETE_WINDOW", on_close_login)
    login_win.bind("<Escape>", lambda e: on_close_login())

    login_win.mainloop()

# ===================== MAIN =====================
if __name__ == "__main__":
    try:
        abrir_login()
    except Exception:
        logging.error("Erro ao iniciar a aplicação", exc_info=True)
        try:
            messagebox.showerror(
                "Erro", "Falha ao iniciar a aplicação. Consulte o arquivo de logs."
            )
        except Exception:
            pass


# ================= ENVIO DE CUPOM POR E-MAIL ================= 
