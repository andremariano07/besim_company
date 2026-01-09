# -*- coding: utf-8 -*-
"""
Sistema Loja - versão unificada com auto-update (após login), splash estilizada e barra de progresso real.
Garantias:
- Roda sem erro
- Atualiza apenas uma vez (sem loop)
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
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import sqlite3
import datetime
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
import certifi
from functools import partial
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ===================== CONFIGURAÇÕES =====================
APP_VERSION = "1.5"
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
    format="%(asctime)s [%(levelname)s] %(message)s"
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
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valor REAL,
    data TEXT
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
        cursor.execute("SELECT username, is_admin FROM users WHERE username=?", ("admin",))
        r = cursor.fetchone()
        if not r:
            cursor.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,1)",
                ("admin", hash_password("admin123"))
            )
            conn.commit()
        else:
            if r[1] != 1:
                cursor.execute("UPDATE users SET is_admin=1 WHERE username=?", ("admin",))
                conn.commit()
    except Exception:
        pass

ensure_admin_user()

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
                root.attributes('-topmost', True)
                root.after(200, lambda: root.attributes('-topmost', False))
            except Exception:
                pass
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
            self.attributes('-topmost', True)
            self.lift()
            self.focus_force()
            self.after(10, self.lift)
            self.after(20, lambda: self.attributes('-topmost', True))
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
                tk.Label(frame, text="BESIM COMPANY", fg="white", bg="#1e1e1e",
                         font=("Segoe UI", 20, "bold")).pack(pady=(55, 20))
        else:
            tk.Label(frame, text="BESIM COMPANY", fg="white", bg="#1e1e1e",
                     font=("Segoe UI", 20, "bold")).pack(pady=(55, 20))
        tk.Label(frame, text="Atualizando sistema...", fg="#cccccc",
                 bg="#1e1e1e", font=("Segoe UI", 12)).pack()
        self.progress = ttk.Progressbar(frame, orient="horizontal",
                                         length=360, mode="determinate")
        self.progress.pack(pady=25)
        self.status = tk.Label(frame, text="Preparando atualização",
                               fg="#9cdcfe", bg="#1e1e1e",
                               font=("Segoe UI", 10))
        self.status.pack()

    def set_progress(self, value):
        self.progress['value'] = value
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

# ===================== UPDATE (após login, corrigido) =====================
def obter_versao_remota():
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{VERSION_FILE}"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=10) as r:
        return r.read().decode("utf-8").strip()


def baixar_e_extrair(splash: SplashScreen):
    zip_url = f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip"
    temp_dir = tempfile.mkdtemp(prefix="update_")
    zip_path = os.path.join(temp_dir, "repo.zip")
    splash.set_status("Baixando atualização...")
    splash.set_progress(5)
    with urllib.request.urlopen(zip_url, context=_SSL_CTX) as response:
        total = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        with open(zip_path, 'wb') as out:
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
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(temp_dir)
    splash.set_status("Copiando nova versão...")
    splash.set_progress(85)
    src_dir = next(os.scandir(temp_dir)).path
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel = os.path.relpath(root, src_dir)
        dest = os.path.join(os.getcwd(), rel)
        os.makedirs(dest, exist_ok=True)
        for f in files:
            if f not in IGNORE_FILES:
                shutil.copy2(os.path.join(root, f), os.path.join(dest, f))
    splash.set_status("Finalizando...")
    splash.set_progress(100)


def check_and_update_after_login(master: tk.Misc) -> bool:
    """Retorna True se atualizar (e reiniciar), False caso contrário."""
    try:
        remote_version = obter_versao_remota()
        if remote_version == APP_VERSION:
            return False
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

        baixar_e_extrair(splash)
        splash.set_status("Atualização concluída. Reiniciando...")

        # Reforçar visibilidade antes do reinício
        try:
            splash.lift()
            splash.focus_force()
            splash.update()
        except Exception:
            pass

        master.after(1200, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))
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
    nome_arquivo = os.path.join(pasta_cupons, f"cupom_{agora.strftime('%Y%m%d_%H%M%S')}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), 40, 730, width=150, height=50, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY",
        "--------------------------------",
        f"Cliente: {cliente}",
        f"Produto: {produto}",
        f"Quantidade: {qtd}",
        f"Forma de Pagamento: {pagamento}",
        f"Total: R$ {total:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        f"Hora: {agora.strftime('%H:%M:%S')}",
        "--------------------------------",
        "Obrigado pela preferência!"
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
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
    # Recoloca a janela do app na frente
    bring_app_to_front()


def gerar_os_pdf(os_num, nome, cpf, telefone, descricao, valor):
    agora = datetime.datetime.now()
    pasta_os = os.path.join(os.getcwd(), "OS")
    os.makedirs(pasta_os, exist_ok=True)
    nome_arquivo = os.path.join(pasta_os, f"OS_{os_num}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), 40, 730, width=150, height=50, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    t = c.beginText(40, 680)
    t.setFont("Helvetica", 12)
    linhas = [
        "BESIM COMPANY - ORDEM DE SERVIÇO",
        "--------------------------------",
        f"OS Nº: {os_num}",
        f"Cliente: {nome}",
        f"CPF: {cpf}",
        f"Telefone: {telefone}",
        f"Descrição: {descricao}",
        f"Valor: R$ {valor:.2f}",
        f"Data: {agora.strftime('%d/%m/%Y')}",
        "--------------------------------"
    ]
    for l in linhas:
        t.textLine(l)
    c.drawText(t)
    c.save()
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
    nome_arquivo = os.path.join(pasta_rel, f"relatorio_vendas_{data_alvo.replace('/', '-')}.pdf")
    c = canvas.Canvas(nome_arquivo, pagesize=A4)
    logo_path_local = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path_local):
        try:
            c.drawImage(ImageReader(logo_path_local), 40, 780, width=140, height=40, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
    c.setFont("Helvetica", 11)
    c.drawString(40, 742, "--------------------------------------------")
    y = 720
    cursor.execute(
        """
        SELECT hora, cliente, produto, quantidade, pagamento, total
        FROM vendas
        WHERE data=?
        ORDER BY hora DESC
        """,
        (data_alvo,)
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
            total_dia += (total or 0.0)
            if pagamento in totais_pg:
                totais_pg[pagamento] += (total or 0.0)
            else:
                totais_pg["OUTROS"] += (total or 0.0)
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
                        c.drawImage(ImageReader(logo_path_local), 40, 780, width=140, height=40, preserveAspectRatio=True, mask='auto')
                    except Exception:
                        pass
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, 760, f"Relatório de Vendas - {data_alvo}")
                c.setFont("Helvetica", 11)
                c.drawString(40, 742, "--------------------------------------------")
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
    y -= 8
    c.setFont("Helvetica", 11)
    c.drawString(40, y, "--------------------------------------------")
    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Totais por Forma de Pagamento:")
    c.setFont("Helvetica", 11)
    y -= 18
    for k in ["PIX", "Cartão", "Dinheiro", "OUTROS"]:
        c.drawString(40, y, f"{k}: R$ {totais_pg[k]:.2f}")
        y -= 18
    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Total do dia: R$ {total_dia:.2f}")
    c.save()
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
    texto = ''.join(filter(str.isdigit, entry.get()))[:11]
    novo = ''
    for i, c in enumerate(texto):
        if i == 3 or i == 6:
            novo += '.'
        if i == 9:
            novo += '-'
        novo += c
    entry.delete(0, 'end')
    entry.insert(0, novo)


def formatar_telefone(event, entry):
    texto = ''.join(filter(str.isdigit, entry.get()))[:11]
    novo = ''
    for i, c in enumerate(texto):
        if i == 0:
            novo += '('
        if i == 2:
            novo += ') '
        if i == 7:
            novo += '-'
        novo += c
    entry.delete(0, 'end')
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
    root.title(f"BESIM COMPANY - Usuário: {username}")
    root.geometry("1280x720")
    root.minsize(1100, 600)
    root.lift()
    root.focus_force()
    root.attributes('-topmost', True)
    root.after(200, lambda: root.attributes('-topmost', False))

    setup_global_exception_handlers(root)

    # Executa atualização após login (se houver)
    try:
        updated = check_and_update_after_login(root)
        if updated:
            return  # app será reiniciado
    except Exception:
        pass

    closing_state = {'mode': None}

    def on_close():
        if closing_state.get('mode') == 'logout':
            try:
                root.destroy()
            except Exception:
                pass
            try:
                if login_win and login_win.winfo_exists():
                    login_win.deiconify()
                    login_win.lift()
                    login_win.focus_force()
                    if hasattr(login_win, 'ent_user'):
                        login_win.ent_user.delete(0, 'end')
                    if hasattr(login_win, 'ent_pass'):
                        login_win.ent_pass.delete(0, 'end')
            except Exception:
                pass
            closing_state['mode'] = None
            return
        if messagebox.askyesno("Sair", "Tem certeza que deseja encerrar o sistema?"):
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
        else:
            return

    root.protocol("WM_DELETE_WINDOW", on_close)

    menu_bar = tk.Menu(root)
    menu_sessao = tk.Menu(menu_bar, tearoff=0)

    def do_logout():
        if messagebox.askyesno("Logout", "Deseja finalizar a sessão e voltar ao login?"):
            closing_state['mode'] = 'logout'
            on_close()
    def do_quit():
        closing_state['mode'] = None
        on_close()

    menu_sessao.add_command(label="Logout", accelerator="Ctrl+L", command=do_logout)
    menu_sessao.add_separator()
    menu_sessao.add_command(label="Sair", accelerator="Ctrl+Q", command=do_quit)
    menu_bar.add_cascade(label="Sessão", menu=menu_sessao)
    root.config(menu=menu_bar)
    root.bind_all("<Control-l>", lambda e: do_logout())
    root.bind_all("<Control-q>", lambda e: do_quit())

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
    style.map("TButton", foreground=[("active", "#000000")])
    style.configure("TNotebook.Tab", padding=[12, 8], font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", tabposition='n')
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    header = ttk.Frame(root)
    header.pack(fill="x", padx=12, pady=(8, 0))

    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((180, 54))
            log_img = ImageTk.PhotoImage(img)
            lbl_logo = ttk.Label(header, image=log_img)
            lbl_logo.image = log_img
            lbl_logo.pack(side="left")
        except Exception:
            ttk.Label(header, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(side="left")
    else:
        ttk.Label(header, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(side="left")

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

    # ====== ESTOQUE ====== (conteúdo igual ao fix anterior)
    est_top = ttk.Frame(aba_estoque)
    est_top.pack(fill="both", expand=True)
    tree_frame = ttk.Frame(est_top)
    tree_frame.pack(fill="both", expand=True, pady=(0, 8))
    tree = ttk.Treeview(tree_frame, columns=("Código", "Nome", "Tipo", "Preço", "Qtd"), show="headings", selectmode="browse")
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
    ent_tipo = ttk.Combobox(frm_tipo, values=["Produto", "Acessório", "Manutenção"], width=16)
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
        tree.tag_configure('baixo', background='tomato')
        tree.tag_configure('laranja', background='orange')
        tree.tag_configure('verde', background='lightgreen')
        for p in cursor.execute("SELECT codigo,nome,tipo,preco,estoque FROM produtos"):
            qtd = p[4]
            if qtd <= 5:
                tag = 'baixo'
            elif 6 <= qtd <= 7:
                tag = 'laranja'
            else:
                tag = 'verde'
            tree.insert("", "end", values=(p[0], p[1], p[2], f"R$ {p[3]:.2f}", qtd), tags=(tag,))
    listar_estoque()

    btn_frame_est = ttk.Frame(aba_estoque)
    btn_frame_est.pack(fill="x", pady=(6, 0))

    def cadastrar_produto():
        try:
            codigo = ent_codigo.get().strip()
            nome = ent_nome.get().strip()
            tipo = ent_tipo.get().strip()
            custo = float(ent_custo.get().replace("R$", "").replace(",", ".")) if ent_custo.get() else 0
            preco = float(ent_preco.get().replace("R$", "").replace(",", ".")) if ent_preco.get() else 0
            qtd = int(ent_qtd.get() or 0)
            if not codigo or not nome or not tipo:
                messagebox.showwarning("Atenção", "Preencha todos os campos")
                return
            with conn:
                cursor.execute(
                    "INSERT INTO produtos (codigo,nome,tipo,custo,preco,estoque) VALUES (?,?,?,?,?,?)",
                    (codigo, nome, tipo, custo, preco, qtd)
                )
            listar_estoque()
            messagebox.showinfo("OK", "Produto cadastrado!")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Código já existe!")
        except ValueError:
            messagebox.showerror("Erro", "Digite números válidos")

    def excluir_produto():
        if not is_admin(username):
            messagebox.showerror("Permissão negada", "Somente o administrador pode excluir produtos.")
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
            messagebox.showwarning("Atenção", "Nenhum produto carregado para edição. Clique em 'Editar (carregar)' primeiro.")
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
            if not messagebox.askyesno("Salvar Edição", f"Deseja salvar as alterações do produto {codigo}?"):
                return
            with conn:
                cursor.execute(
                    """
                    UPDATE produtos
                    SET nome=?, tipo=?, custo=?, preco=?, estoque=?
                    WHERE codigo=?
                    """,
                    (nome, tipo, custo, preco, qtd, codigo)
                )
            listar_estoque()
            messagebox.showinfo("Sucesso", "Produto atualizado com sucesso!")
            ent_codigo.config(state="normal")
            ent_codigo.delete(0, "end")
        except ValueError:
            messagebox.showerror("Erro", "Valores inválidos")

    tree.bind("<Double-1>", lambda e: carregar_produto_selecionado())
    btn_cad_prod = ttk.Button(btn_frame_est, text="Cadastrar", command=cadastrar_produto)
    btn_edit_load_prod = ttk.Button(btn_frame_est, text="Editar (carregar)", command=carregar_produto_selecionado)
    btn_save_edit_prod = ttk.Button(btn_frame_est, text="Salvar Edição", command=salvar_edicao_produto)
    btn_del_prod = ttk.Button(btn_frame_est, text="Excluir", command=excluir_produto)
    btn_cad_prod.pack(side="left", padx=6)
    btn_edit_load_prod.pack(side="left", padx=6)
    btn_save_edit_prod.pack(side="left", padx=6)
    btn_del_prod.pack(side="left", padx=6)
    if not is_admin(username):
        btn_del_prod.state(["disabled"]) 

    # ====== CLIENTES ======
    f_cli = ttk.Frame(aba_clientes, padding=8)
    f_cli.pack(fill="x", pady=6)
    ttk.Label(f_cli, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_c = ttk.Entry(f_cli)
    ent_cpf_c.grid(row=0, column=1, padx=6, pady=4)
    ttk.Label(f_cli, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_c = ttk.Entry(f_cli)
    ent_nome_c.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_cli, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_c = ttk.Entry(f_cli)
    ent_tel_c.grid(row=0, column=5, padx=6, pady=4)
    ent_cpf_c.bind("<KeyRelease>", lambda e: formatar_cpf(e, ent_cpf_c))
    ent_cpf_c.bind("<FocusOut>", lambda e: formatar_cpf(e, ent_cpf_c))
    ent_tel_c.bind("<KeyRelease>", lambda e: formatar_telefone(e, ent_tel_c))

    def cadastrar_cliente():
        cpf = ent_cpf_c.get().strip()
        nome = ent_nome_c.get().strip()
        tel = ent_tel_c.get().strip()
        if not cpf or not nome or not tel:
            messagebox.showwarning("Atenção", "Preencha todos os campos")
            return
        with conn:
            cursor.execute("INSERT OR REPLACE INTO clientes (cpf,nome,telefone) VALUES (?,?,?)", (cpf, nome, tel))
        messagebox.showinfo("OK", "Cliente cadastrado")

    ttk.Button(f_cli, text="Cadastrar Cliente", command=cadastrar_cliente).grid(row=1, column=1, pady=10, sticky="w")

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
    ttk.Label(f_v, text="Código Produto").grid(row=1, column=0, sticky="w", padx=6, pady=4)
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
            cursor.execute("SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,))
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

    ttk.Checkbutton(f_v, text="5%", variable=var_desc_5, command=lambda: [var_desc_10.set(0), atualizar_total()]).grid(row=4, column=0, sticky="w", padx=6)
    ttk.Checkbutton(f_v, text="10%", variable=var_desc_10, command=lambda: [var_desc_5.set(0), atualizar_total()]).grid(row=4, column=1, sticky="w", padx=6)

    def buscar_cliente_v():
        cpf = ent_cpf_v.get().strip()
        cursor.execute("SELECT nome,telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_v.delete(0, "end")
            ent_nome_v.insert(0, r[0])

    ttk.Button(f_v, text="Buscar Cliente", command=buscar_cliente_v).grid(row=0, column=4, padx=6)

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
            cursor.execute("SELECT nome,preco,estoque FROM produtos WHERE codigo=?", (codigo,))
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
                    (cliente, cpf, nome_prod, qtd, total, pagamento, data, hora)
                )
                cursor.execute("UPDATE produtos SET estoque=? WHERE codigo=?", (estoque - qtd, codigo))
                cursor.execute("INSERT INTO caixa(valor,data) VALUES (?,?)", (total, data))
                cursor.execute("INSERT OR IGNORE INTO clientes(cpf,nome) VALUES (?,?)", (cpf, cliente))
            listar_estoque()
            try:
                gerar_cupom(cliente or '', nome_prod, qtd, pagamento or '', total)
            except Exception:
                pass
            messagebox.showinfo("Venda", "Venda realizada!\nTotal: R$ {:.2f}".format(total))
            carregar_vendas_dia()
            ent_cod_v.delete(0, "end")
            ent_qtd_v.delete(0, "end")
            ent_prod_v.config(state="normal")
            ent_prod_v.delete(0, "end")
            ent_prod_v.config(state="readonly")
            ent_pg_v.set("")
            lbl_total_v.config(text="Total: R$ 0.00")
            var_desc_5.set(0)
            var_desc_10.set(0)
        except Exception as ex:
            messagebox.showerror("Erro", f"Ocorreu um erro na venda\n{ex}")

    ttk.Button(f_v, text="Finalizar Venda", command=finalizar_venda).grid(row=5, column=0, columnspan=2, pady=10, sticky="w", padx=6)

    hist_v_frame = ttk.Frame(aba_vendas, padding=(8, 0))
    hist_v_frame.pack(fill="both", expand=True)
    top_hist = ttk.Frame(hist_v_frame)
    top_hist.pack(fill="x", pady=(6, 6))
    lbl_hist = ttk.Label(top_hist, text="Vendas de Hoje", font=("Segoe UI", 11, "bold"))
    lbl_hist.pack(side="left", padx=6)
    ttk.Button(top_hist, text="Atualizar", command=lambda: carregar_vendas_dia()).pack(side="left", padx=6)
    ttk.Button(top_hist, text="Exportar PDF", command=lambda: gerar_relatorio_vendas_dia_pdf()).pack(side="left", padx=6)
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
        height=10
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
    tree_vendas.tag_configure('PIX', background='#e6ffed')
    tree_vendas.tag_configure('Cartão', background='#e6f0ff')
    tree_vendas.tag_configure('Dinheiro', background='#fff5e6')
    tree_vendas.tag_configure('default', background='white')

    def carregar_vendas_dia():
        tree_vendas.delete(*tree_vendas.get_children())
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        filtro = combo_filtro_pg.get().strip()
        if filtro:
            cursor.execute(
                """
                SELECT hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=? AND pagamento=?
                ORDER BY hora DESC
                """,
                (hoje, filtro)
            )
        else:
            cursor.execute(
                """
                SELECT hora, cliente, produto, quantidade, pagamento, total
                FROM vendas
                WHERE data=?
                ORDER BY hora DESC
                """,
                (hoje,)
            )
        for hora, cliente, produto, qtd, pagamento, total in cursor.fetchall():
            tag = pagamento if pagamento in ("PIX", "Cartão", "Dinheiro") else 'default'
            tree_vendas.insert("", "end", values=(hora, cliente, produto, qtd, pagamento, f"R$ {total:.2f}"), tags=(tag,))

    combo_filtro_pg.bind("<<ComboboxSelected>>", lambda e: carregar_vendas_dia())

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
    ent_saida_cx = ttk.Entry(frm_saida, width=20)
    ent_saida_cx.pack(anchor="w", pady=4)
    ent_saida_cx.bind("<FocusOut>", lambda e: formatar_moeda(e, ent_saida_cx))

    def registrar_saida_caixa():
        valor_text = ent_saida_cx.get().replace("R$", "").replace(",", ".").strip()
        if not valor_text:
            messagebox.showwarning("Atenção", "Informe o valor da saída")
            return
        try:
            valor = float(valor_text)
            if valor <= 0:
                messagebox.showwarning("Atenção", "Informe um valor positivo para a saída")
                return
            hoje = datetime.datetime.now().strftime("%d/%m/%Y")
            with conn:
                cursor.execute("INSERT INTO caixa(valor,data) VALUES (?,?)", (-valor, hoje))
            ent_saida_cx.delete(0, "end")
            atualizar_caixa()
            messagebox.showinfo("Saída", f"Saída de R$ {valor:.2f} registrada com sucesso")
        except ValueError:
            messagebox.showerror("Erro", "Valor inválido")

    ttk.Button(caixa_ops, text="Registrar Saída", command=registrar_saida_caixa).pack(side="left", padx=6, pady=10)
    ttk.Separator(f_cx, orient="horizontal").pack(fill="x", pady=6)

    tree_cx_frame = ttk.Frame(f_cx)
    tree_cx_frame.pack(fill="both", expand=True)
    tree_cx = ttk.Treeview(tree_cx_frame, columns=("Data", "Total"), show="headings", height=8)
    tree_cx.heading("Data", text="Data")
    tree_cx.heading("Total", text="Total Fechado")
    tree_cx.column("Data", width=200, anchor="center")
    tree_cx.column("Total", width=200, anchor="e")
    tree_cx.pack(side="left", fill="both", expand=True, padx=(0, 6))
    scrollbar_cx = ttk.Scrollbar(tree_cx_frame, orient="vertical", command=tree_cx.yview)
    tree_cx.configure(yscroll=scrollbar_cx.set)
    scrollbar_cx.pack(side="right", fill="y")

    def carregar_historico_cx():
        try:
            if not tree_cx.winfo_exists():
                return
            tree_cx.delete(*tree_cx.get_children())
            for row in cursor.execute("SELECT data,total FROM fechamento_caixa ORDER BY data DESC"):
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
                    cursor.execute("INSERT OR REPLACE INTO fechamento_caixa (data,total) VALUES (?,?)", (ultima_data, total_ultimo))
                    cursor.execute("DELETE FROM caixa WHERE data=?", (ultima_data,))
                conn.commit()
        cursor.execute("SELECT SUM(valor) FROM caixa WHERE data=?", (hoje,))
        total_hoje = cursor.fetchone()[0] or 0
        lbl_total_cx.config(text=f"Total arrecadado hoje: R$ {total_hoje:.2f}")
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
        if messagebox.askyesno("Fechar Caixa", f"Total do dia: R$ {total:.2f}\nDeseja fechar o caixa?"):
            with conn:
                cursor.execute("INSERT OR REPLACE INTO fechamento_caixa(data,total) VALUES (?,?)", (hoje, total))
                cursor.execute("DELETE FROM caixa WHERE data=?", (hoje,))
            pdf_path = gerar_relatorio_vendas_dia_pdf(data_str=hoje)
            messagebox.showinfo("Fechar Caixa", f"Caixa do dia {hoje} fechado com sucesso!\nRelatório gerado:\n{pdf_path}")
            carregar_historico_cx()
            atualizar_caixa()

    carregar_historico_cx()
    atualizar_caixa()
    ttk.Button(f_cx, text="Fechar Caixa Manualmente", command=fechar_caixa).pack(pady=8)

    # ====== MANUTENÇÃO ======
    f_m = ttk.Frame(aba_manutencao, padding=8)
    f_m.pack(fill="x", pady=6)
    ttk.Label(f_m, text="CPF").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_cpf_m = ttk.Entry(f_m)
    ent_cpf_m.grid(row=0, column=1, padx=6, pady=4)
    ent_cpf_m.bind("<KeyRelease>", partial(formatar_cpf, entry=ent_cpf_m))
    ttk.Label(f_m, text="Nome").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_nome_m = ttk.Entry(f_m, state="readonly")
    ent_nome_m.grid(row=0, column=3, padx=6, pady=4)
    ttk.Label(f_m, text="Telefone").grid(row=0, column=4, sticky="w", padx=6, pady=4)
    ent_tel_m = ttk.Entry(f_m, state="readonly")
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
    tree_m = ttk.Treeview(tree_m_frame, columns=("OS", "Nome", "CPF", "Telefone", "Descrição", "Data", "Valor", "Aprovado"), show="headings")
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
        for row in cursor.execute("SELECT os, nome, cpf, telefone, descricao, data, COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao ORDER BY os DESC"):
            aprovado_text = "Sim" if row[7] == 1 else "Não"
            tree_m.insert("", "end", values=(row[0], row[1], row[2], row[3], row[4], row[5], f"R$ {row[6]:.2f}", aprovado_text))
    carregar_manutencao()

    def buscar_cliente_m(event=None):
        cpf = ent_cpf_m.get().strip()
        cursor.execute("SELECT nome, telefone FROM clientes WHERE cpf=?", (cpf,))
        r = cursor.fetchone()
        if r:
            ent_nome_m.config(state="normal")
            ent_nome_m.delete(0, "end")
            ent_nome_m.insert(0, r[0])
            ent_nome_m.config(state="readonly")
            ent_tel_m.config(state="normal")
            ent_tel_m.delete(0, "end")
            ent_tel_m.insert(0, r[1])
            ent_tel_m.config(state="readonly")

    ent_cpf_m.bind("<FocusOut>", buscar_cliente_m)
    ttk.Button(f_m, text="Buscar Cliente", command=buscar_cliente_m).grid(row=0, column=6, padx=6)

    def cadastrar_manutencao():
        cpf = ent_cpf_m.get().strip()
        nome = ent_nome_m.get().strip()
        telefone = ent_tel_m.get().strip()
        desc = ent_desc_m.get().strip()
        valor_text = ent_valor_m.get().replace("R$", "").replace(",", ".").strip()
        if not cpf or not nome or not desc or not valor_text:
            messagebox.showwarning("Atenção", "Preencha todos os campos, incluindo o valor")
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
                (cpf, nome, telefone, desc, data, valor)
            )
            os_num = cursor.lastrowid
        gerar_os_pdf(os_num, nome, cpf, telefone, desc, valor)
        carregar_manutencao()
        ent_cpf_m.delete(0, "end")
        ent_nome_m.config(state="normal"); ent_nome_m.delete(0, "end"); ent_nome_m.config(state="readonly")
        ent_tel_m.config(state="normal"); ent_tel_m.delete(0, "end"); ent_tel_m.config(state="readonly")
        ent_desc_m.delete(0, "end")
        ent_valor_m.delete(0, "end")
        messagebox.showinfo("OS", "Ordem de serviço registrada!")

    btn_reg_manut = ttk.Button(f_m, text="Registrar Manutenção", command=cadastrar_manutencao)
    btn_reg_manut.grid(row=2, column=0, columnspan=2, pady=8)
    btn_excluir_manut = ttk.Button(f_m, text="Excluir Manutenção", command=lambda: excluir_manutencao())
    btn_excluir_manut.grid(row=2, column=2, columnspan=2, pady=8)
    if not is_admin(username):
        btn_excluir_manut.state(["disabled"]) 

    def excluir_manutencao():
        if not is_admin(username):
            messagebox.showerror("Permissão negada", "Somente o administrador pode excluir manutenções.")
            return
        item = tree_m.selection()
        if not item:
            return
        os_num = tree_m.item(item)["values"][0]
        if messagebox.askyesno("Excluir OS", f"Deseja excluir a OS {os_num}?"):
            with conn:
                cursor.execute("DELETE FROM manutencao WHERE os=?", (os_num,))
            carregar_manutencao()

    def aprovar_manutencao():
        item = tree_m.selection()
        if not item:
            messagebox.showwarning("Atenção", "Selecione a OS que será aprovada na lista.")
            return
        os_num = tree_m.item(item)["values"][0]
        cursor.execute("SELECT COALESCE(valor,0), COALESCE(aprovado,0) FROM manutencao WHERE os=?", (os_num,))
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
        try:
            with conn:
                cursor.execute("INSERT INTO caixa(valor,data) VALUES (?,?)", (valor, hoje))
                cursor.execute("UPDATE manutencao SET aprovado=1 WHERE os=?", (os_num,))
            carregar_manutencao()
            atualizar_caixa()
            messagebox.showinfo("Aprovado", f"OS {os_num} aprovada. R$ {valor:.2f} adicionados ao caixa.")
        except Exception:
            messagebox.showerror("Erro", "Falha ao aprovar manutenção. Tente novamente.")

    ttk.Button(f_m, text="Manutenção Aprovada", command=aprovar_manutencao).grid(row=2, column=4, columnspan=2, pady=8)

    # ====== DEVOLUÇÃO ======
    f_d = ttk.Frame(aba_devolucao, padding=8)
    f_d.pack(fill="x", pady=6)
    ttk.Label(f_d, text="Quem devolve").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    ent_nome_dev = ttk.Entry(f_d, width=30)
    ent_nome_dev.grid(row=0, column=1, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Qual a devolução").grid(row=0, column=2, sticky="w", padx=6, pady=4)
    ent_devolucao = ttk.Entry(f_d, width=40)
    ent_devolucao.grid(row=0, column=3, padx=6, pady=4, sticky="w")
    ttk.Label(f_d, text="Motivo da devolução").grid(row=1, column=0, sticky="w", padx=6, pady=4)
    ent_motivo_dev = ttk.Entry(f_d, width=80)
    ent_motivo_dev.grid(row=1, column=1, columnspan=3, padx=6, pady=4, sticky="we")

    hist_d_frame = ttk.Frame(aba_devolucao, padding=(8, 0))
    hist_d_frame.pack(fill="both", expand=True)
    top_hist_d = ttk.Frame(hist_d_frame)
    top_hist_d.pack(fill="x", pady=(6, 6))
    ttk.Label(top_hist_d, text="Histórico de Devoluções", font=("Segoe UI", 11, "bold")).pack(side="left", padx=6)
    ttk.Button(top_hist_d, text="Atualizar", command=lambda: carregar_devolucoes()).pack(side="left", padx=6)

    tree_dev_frame = ttk.Frame(hist_d_frame)
    tree_dev_frame.pack(fill="both", expand=True)
    tree_dev = ttk.Treeview(
        tree_dev_frame,
        columns=("Data", "Hora", "Nome", "Item", "Motivo"),
        show="headings",
        height=10
    )
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
    scrollbar_dev = ttk.Scrollbar(tree_dev_frame, orient="vertical", command=tree_dev.yview)
    tree_dev.configure(yscroll=scrollbar_dev.set)
    scrollbar_dev.pack(side="right", fill="y")

    def carregar_devolucoes():
        tree_dev.delete(*tree_dev.get_children())
        cursor.execute(
            """
            SELECT data, hora, nome, item, motivo
            FROM devolucoes
            ORDER BY date(substr(data,7,4)||'-'||substr(data,4,2)||'-'||substr(data,1,2)) DESC, hora DESC
            """
        )
        for data, hora, nome, item, motivo in cursor.fetchall():
            tree_dev.insert("", "end", values=(data, hora, nome, item, motivo))

    def registrar_devolucao():
        nome = ent_nome_dev.get().strip()
        item = ent_devolucao.get().strip()
        motivo = ent_motivo_dev.get().strip()
        if not nome or not item or not motivo:
            messagebox.showwarning("Atenção", "Preencha nome, item e motivo da devolução")
            return
        data = datetime.datetime.now().strftime("%d/%m/%Y")
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with conn:
                cursor.execute(
                    "INSERT INTO devolucoes(item,motivo,nome,data,hora) VALUES (?,?,?,?,?)",
                    (item, motivo, nome, data, hora)
                )
            messagebox.showinfo("Devolução", "Devolução registrada com sucesso!")
            ent_nome_dev.delete(0, "end")
            ent_devolucao.delete(0, "end")
            ent_motivo_dev.delete(0, "end")
            carregar_devolucoes()
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao registrar devolução\n{ex}")

    ttk.Button(f_d, text="Registrar Devolução", command=registrar_devolucao).grid(row=2, column=0, pady=10, sticky="w", padx=6)
    carregar_devolucoes()

    ttk.Separator(root, orient="horizontal").pack(fill="x", padx=8, pady=(2, 2), side="bottom")
    footer_text_main = "Developed by André Mariano\n\nBeta Test"
    ttk.Label(root, text=footer_text_main, style="Footer.TLabel", anchor="center", justify="center").pack(side="bottom", fill="x", pady=(0, 8))

# ================= TELA DE LOGIN =================

def abrir_login():
    login_win = tk.Tk()
    login_win.title("Login - BESIM COMPANY")
    login_win.geometry("420x300")
    login_win.resizable(False, False)
    setup_global_exception_handlers(login_win)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Footer.TLabel", foreground="red", font=("Segoe UI", 10, "bold"))

    frm = ttk.Frame(login_win, padding=12)
    frm.pack(fill="both", expand=True)
    logo_path = os.path.join(os.getcwd(), "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).resize((200, 62))
            logo_img = ImageTk.PhotoImage(img)
            lbl_logo = ttk.Label(frm, image=logo_img)
            lbl_logo.image = logo_img
            lbl_logo.pack(pady=(0, 8))
        except Exception:
            ttk.Label(frm, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))
    else:
        ttk.Label(frm, text="BESIM COMPANY", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))

    ttk.Label(frm, text="Usuário").pack(anchor="w", pady=(6, 0))
    ent_user = ttk.Entry(frm)
    ent_user.pack(fill="x", pady=4)

    ttk.Label(frm, text="Senha").pack(anchor="w", pady=(6, 0))
    ent_pass = ttk.Entry(frm, show="*")
    ent_pass.pack(fill="x", pady=4)

    login_win.ent_user = ent_user
    login_win.ent_pass = ent_pass

    def tentar_login():
        user = ent_user.get().strip()
        pw = ent_pass.get().strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha")
            return
        cursor.execute("SELECT password_hash FROM users WHERE username=?", (user,))
        r = cursor.fetchone()
        if not r:
            messagebox.showerror("Erro", "Usuário não encontrado")
            return
        if hash_password(pw) == r[0]:
            login_win.withdraw()
            try:
                abrir_sistema_com_logo(user, login_win)
            except Exception as ex:
                messagebox.showerror("Erro fatal", f"Falha ao abrir a janela principal:\n{ex}")
                login_win.deiconify()
        else:
            messagebox.showerror("Erro", "Senha incorreta")

    def criar_usuario():
        user = ent_user.get().strip()
        pw = ent_pass.get().strip()
        if not user or not pw:
            messagebox.showwarning("Atenção", "Informe usuário e senha para criar")
            return
        try:
            with conn:
                cursor.execute(
                    "INSERT INTO users(username,password_hash,is_admin) VALUES (?,?,0)",
                    (user, hash_password(pw))
                )
            messagebox.showinfo("OK", "Usuário criado com sucesso")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Usuário já existe")

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(fill="x", pady=12)
    ttk.Button(btn_frame, text="Entrar", command=tentar_login).pack(side="left", expand=True, padx=6)
    ttk.Button(btn_frame, text="Criar Usuário", command=criar_usuario).pack(side="left", expand=True, padx=6)

    ttk.Separator(login_win, orient="horizontal").pack(fill="x", padx=8, pady=(4, 2), side="bottom")
    footer_text = "Developed by André Mariano\n\nBeta Test"
    ttk.Label(login_win, text=footer_text, style="Footer.TLabel", anchor="center", justify="center").pack(side="bottom", fill="x", pady=(0, 8))

    def on_close_login():
        if messagebox.askyesno("Sair", "Deseja encerrar o sistema?"):
            try:
                conn.close()
            except Exception:
                pass
            login_win.destroy()
        else:
            return

    login_win.protocol("WM_DELETE_WINDOW", on_close_login)
    login_win.mainloop()

# ===================== MAIN =====================
if __name__ == "__main__":
    try:
        abrir_login()
    except Exception:
        logging.error("Erro ao iniciar a aplicação", exc_info=True)
        try:
            messagebox.showerror("Erro", "Falha ao iniciar a aplicação. Consulte o arquivo de logs.")
        except Exception:
            pass
