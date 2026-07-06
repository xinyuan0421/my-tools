#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求对比可视化工具 v3 — 含导出、忽略、自动判断非差异"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv, difflib, os, re, subprocess, tempfile, threading, zipfile

# ═══════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════
SKIP_PATTERNS = [
    r'^\d+\.\d+.*', r'^属性:$', r'^Requirement ID:',
    r'^Fault Tolerant Time', r'^Interval:', r'^Safety State:',
    r'^x0[0-9a-fA-F]+', r'^楚能汽车',
]
NOISE_RE = re.compile(
    r'^\(1\)\s*=>\s*.*$|^Description\s+(modified|Reference)|^x04[0-9a-fA-F]+',
    re.IGNORECASE
)
# 这些标签视为"非实质差异"，可自动忽略
NON_DIFF_LABELS = {'表述差异', '格式/空行差异'}

LABEL_COLOR = {
    '配置字差异':    '#e17055',
    '信号差异':      '#6c5ce7',
    '数值/参数差异': '#fdcb6e',
    'B内容新增':     '#00b894',
    'A内容更多':     '#0984e3',
    '内容差异':      '#d63031',
    '表述差异':      '#b2bec3',
    '格式/空行差异': '#b2bec3',
    '仅A有':         '#fdcb6e',
    '仅B有':         '#74b9ff',
    '':              '#b2bec3',
}
STATUS_MAP = {
    'diff':   '⚡ 有差异',
    'same':   '✅ 相同',
    'only_a': '🔶 仅A有',
    'only_b': '🔷 仅B有',
}

# ═══════════════════════════════════════════════════════
#  数据处理
# ═══════════════════════════════════════════════════════
def strip_title(text):
    return '\n'.join(
        l for l in text.splitlines()
        if not any(re.match(p, l.strip()) for p in SKIP_PATTERNS)
    ).strip()

def xls_to_dict(xls_path):
    tmp_dir = tempfile.mkdtemp()
    r = subprocess.run(
        ['libreoffice', '--headless',
         '--convert-to', 'csv:Text - txt - csv (StarCalc):44,34,76',
         xls_path, '--outdir', tmp_dir],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"LibreOffice 转换失败:\n{r.stderr}")
    base = os.path.splitext(os.path.basename(xls_path))[0]
    csv_path = os.path.join(tmp_dir, base + '.csv')
    if not os.path.exists(csv_path):
        raise RuntimeError(f"找不到转换后的 CSV: {csv_path}")
    data = {}
    with open(csv_path, encoding='utf-8') as f:
        for row in csv.reader(f):
            if row:
                data[row[0].strip()] = row[1].strip() if len(row) > 1 else ''
    return data

def build_diff(t1, t2):
    lines1, lines2 = t1.splitlines(), t2.splitlines()
    diff = list(difflib.unified_diff(lines1, lines2, lineterm=''))
    removed = [l[1:] for l in diff if l.startswith('-') and not l.startswith('---') and l[1:].strip()]
    added   = [l[1:] for l in diff if l.startswith('+') and not l.startswith('+++') and l[1:].strip()]
    parts = []
    if removed: parts.append('【A有B无】\n' + '\n'.join(removed))
    if added:   parts.append('【B有A无】\n' + '\n'.join(added))
    return '\n\n'.join(parts)

def classify_diff(diff_text, c1, c2):
    if not diff_text:
        return ''
    a_lines, b_lines = [], []
    bucket = None
    for line in diff_text.splitlines():
        if line == '【A有B无】':   bucket = a_lines
        elif line == '【B有A无】': bucket = b_lines
        elif bucket is not None and line.strip():
            bucket.append(line.strip())
    def clean(lines):
        return [l for l in lines if not NOISE_RE.match(l) and l not in ('\\', '/')]
    real_a, real_b = clean(a_lines), clean(b_lines)
    all_real = real_a + real_b
    all_text = '\n'.join(all_real)
    def normalize(lines):
        return re.sub(r'[等；；、，,。.\s]', '', ''.join(lines))
    if not all_real:                              return '表述差异'
    if normalize(real_a) == normalize(real_b):   return '表述差异'
    if not real_a and real_b and max(len(l) for l in real_b) <= 6: return '表述差异'
    if not real_b and real_a and max(len(l) for l in real_a) <= 6: return '表述差异'
    if '配置字' in all_text:                     return '配置字差异'
    if re.search(r'SignalName|信号名|[A-Z][A-Za-z0-9]{3,}_[A-Za-z0-9_]+', all_text):
        return '信号差异'
    len_a = len('\n'.join(real_a)); len_b = len('\n'.join(real_b))
    if not real_a and real_b:                    return 'B内容新增'
    if not real_b and real_a:                    return 'A内容更多'
    if len_b > len_a * 2.5 and len_a < 80:      return 'B内容新增'
    if len_a > len_b * 2.5 and len_b < 80:      return 'A内容更多'
    if re.search(r'0x[0-9a-fA-F]+|\b\d+(?:\.\d+)?\s*(?:km/h|ms|s|Hz|%|V|A)\b', all_text):
        return '数值/参数差异'
    return '内容差异'

def compare(d1, d2):
    """返回 list of (req_id, text_a, text_b, diff_text, status, label)"""
    results = []
    for rid in sorted(set(d1) | set(d2), key=lambda x: (0, int(x)) if x.isdigit() else (1, x)):
        if rid in d1 and rid in d2:
            c1, c2 = strip_title(d1[rid]), strip_title(d2[rid])
            if c1 == c2:
                results.append((rid, c1, c2, '', 'same', ''))
            else:
                dt = build_diff(c1, c2)
                label = classify_diff(dt, c1, c2) if dt else '格式/空行差异'
                results.append((rid, c1, c2, dt, 'diff', label))
        elif rid in d1:
            results.append((rid, strip_title(d1[rid]), '', '', 'only_a', '仅A有'))
        else:
            results.append((rid, '', strip_title(d2[rid]), '', 'only_b', '仅B有'))
    return results

# ═══════════════════════════════════════════════════════
#  XLSX 导出（纯 stdlib，无需第三方库）
# ═══════════════════════════════════════════════════════
def export_xlsx(rows, path):
    """rows: list of lists (header + data)"""
    str_index = {}
    all_strings = []
    def sid(s):
        s = str(s)
        if s not in str_index:
            str_index[s] = len(all_strings)
            all_strings.append(s)
        return str_index[s]

    def xe(s):
        return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

    sheet_rows = [[sid(c) for c in row] for row in rows]

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"           ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml"  ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml"      ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/styles.xml"             ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="需求对比" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''
    wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"     Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"        Target="styles.xml"/>
</Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts>
    <font><sz val="10"/><name val="Microsoft YaHei"/></font>
    <font><b/><sz val="10"/><name val="Microsoft YaHei"/></font>
    <font><sz val="10"/><name val="Microsoft YaHei"/><color rgb="FF888888"/></font>
  </fonts>
  <fills>
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF2C3E50"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEEEEEE"/></patternFill></fill>
  </fills>
  <borders><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0"><alignment wrapText="1" vertical="top"/></xf>
  </cellXfs>
</styleSheet>'''

    ss = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          f'count="{len(all_strings)}" uniqueCount="{len(all_strings)}">']
    for s in all_strings:
        ss.append(f'<si><t xml:space="preserve">{xe(s)}</t></si>')
    ss.append('</sst>')

    COLS = 'ABCDEFGHIJ'
    sh = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<cols>'
          '<col min="1" max="1" width="10"  customWidth="1"/>'
          '<col min="2" max="2" width="12"  customWidth="1"/>'
          '<col min="3" max="3" width="14"  customWidth="1"/>'
          '<col min="4" max="4" width="10"  customWidth="1"/>'
          '<col min="5" max="5" width="55"  customWidth="1"/>'
          '<col min="6" max="6" width="55"  customWidth="1"/>'
          '<col min="7" max="7" width="55"  customWidth="1"/>'
          '</cols><sheetData>']
    for r_idx, row in enumerate(sheet_rows):
        rn = r_idx + 1
        style = '1' if r_idx == 0 else '0'
        sh.append(f'<row r="{rn}">')
        for c_idx, v in enumerate(row):
            sh.append(f'<c r="{COLS[c_idx]}{rn}" t="s" s="{style}"><v>{v}</v></c>')
        sh.append('</row>')
    sh.append('</sheetData></worksheet>')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml',   content_types)
        zf.writestr('_rels/.rels',            rels)
        zf.writestr('xl/workbook.xml',        workbook)
        zf.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        zf.writestr('xl/sharedStrings.xml',   '\n'.join(ss))
        zf.writestr('xl/styles.xml',          styles)
        zf.writestr('xl/worksheets/sheet1.xml', ''.join(sh))

# ═══════════════════════════════════════════════════════
#  主界面
# ═══════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('需求对比工具 v3')
        self.geometry('1540x900')
        self.configure(bg='#f0f4f8')
        self.resizable(True, True)
        self._data     = []       # list of 6-tuples
        self._filtered = []       # currently shown
        self._ignored  = set()    # set of req_id strings
        self._build_top()
        self._build_filter()
        self._build_table()
        self._build_detail()
        self._build_status()

    # ── 顶部 ─────────────────────────────────────────
    def _build_top(self):
        top = tk.Frame(self, bg='#2c3e50', pady=10)
        top.pack(fill='x')
        tk.Label(top, text='📊 需求对比工具', font=('Microsoft YaHei', 15, 'bold'),
                 bg='#2c3e50', fg='white').pack(side='left', padx=20)

        right = tk.Frame(top, bg='#2c3e50')
        right.pack(side='right', padx=20)
        self.file_a = tk.StringVar()
        self.file_b = tk.StringVar()
        for label, var in [('A 表格:', self.file_a), ('B 表格:', self.file_b)]:
            row = tk.Frame(right, bg='#2c3e50'); row.pack(fill='x', pady=2)
            tk.Label(row, text=label, bg='#2c3e50', fg='#bdc3c7',
                     width=8, anchor='e').pack(side='left')
            tk.Entry(row, textvariable=var, width=50, bg='#34495e', fg='white',
                     insertbackground='white', relief='flat',
                     font=('Consolas', 9)).pack(side='left', padx=4)
            tk.Button(row, text='选择文件', command=lambda v=var: self._pick(v),
                      bg='#3498db', fg='white', relief='flat',
                      activebackground='#2980b9', cursor='hand2').pack(side='left', padx=2)

        btn_row = tk.Frame(right, bg='#2c3e50'); btn_row.pack(pady=6)
        self.btn_compare = tk.Button(btn_row, text='▶ 开始对比',
                                     command=self._run_compare,
                                     bg='#27ae60', fg='white',
                                     font=('Microsoft YaHei', 10, 'bold'),
                                     relief='flat', padx=16, pady=4,
                                     activebackground='#229954', cursor='hand2')
        self.btn_compare.pack(side='left', padx=4)
        # 自动忽略非差异
        tk.Button(btn_row, text='🔕 自动忽略非差异',
                  command=self._auto_ignore,
                  bg='#7f8c8d', fg='white', relief='flat', padx=12, pady=4,
                  activebackground='#636e72', cursor='hand2').pack(side='left', padx=4)
        # 取消全部忽略
        tk.Button(btn_row, text='↩ 取消全部忽略',
                  command=self._clear_ignored,
                  bg='#7f8c8d', fg='white', relief='flat', padx=12, pady=4,
                  activebackground='#636e72', cursor='hand2').pack(side='left', padx=4)
        # 导出按钮
        tk.Button(btn_row, text='💾 导出结果',
                  command=self._export,
                  bg='#e67e22', fg='white', relief='flat', padx=12, pady=4,
                  activebackground='#ca6f1e', cursor='hand2').pack(side='left', padx=4)

    # ── 过滤栏 ───────────────────────────────────────
    def _build_filter(self):
        bar = tk.Frame(self, bg='#dfe6e9', pady=6, padx=12)
        bar.pack(fill='x')
        tk.Label(bar, text='过滤:', bg='#dfe6e9', font=('Microsoft YaHei', 9)).pack(side='left')
        self.filter_var = tk.StringVar(value='diff')
        for text, val in [('全部','all'),('有差异','diff'),('完全相同','same'),
                          ('仅A有','only_a'),('仅B有','only_b')]:
            tk.Radiobutton(bar, text=text, variable=self.filter_var, value=val,
                           command=self._apply_filter, bg='#dfe6e9',
                           activebackground='#dfe6e9',
                           font=('Microsoft YaHei', 9)).pack(side='left', padx=6)

        tk.Label(bar, text='  |', bg='#dfe6e9', fg='#aaa').pack(side='left', padx=4)
        self.hide_ignored_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text='隐藏已忽略', variable=self.hide_ignored_var,
                       command=self._apply_filter, bg='#dfe6e9',
                       activebackground='#dfe6e9',
                       font=('Microsoft YaHei', 9)).pack(side='left', padx=6)

        tk.Label(bar, text='搜索ID:', bg='#dfe6e9',
                 font=('Microsoft YaHei', 9)).pack(side='left', padx=(16,4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self._apply_filter())
        tk.Entry(bar, textvariable=self.search_var, width=14,
                 font=('Consolas', 9)).pack(side='left')

        self.count_label = tk.Label(bar, text='', bg='#dfe6e9',
                                    font=('Microsoft YaHei', 9), fg='#636e72')
        self.count_label.pack(side='right', padx=12)

    # ── 结果表格 ─────────────────────────────────────
    def _build_table(self):
        frame = tk.Frame(self, bg='#f0f4f8')
        frame.pack(fill='both', expand=False, padx=12, pady=(6,0))

        cols = ('需求ID', '状态', '简洁描述', '忽略', '差异摘要')
        self.tree = ttk.Treeview(frame, columns=cols, show='headings',
                                 height=12, selectmode='browse')
        style = ttk.Style(); style.theme_use('clam')
        style.configure('Treeview', rowheight=26, font=('Microsoft YaHei', 9),
                        background='white', fieldbackground='white')
        style.configure('Treeview.Heading', font=('Microsoft YaHei', 9, 'bold'),
                        background='#2c3e50', foreground='white')
        style.map('Treeview', background=[('selected','#3498db')])

        self.tree.heading('需求ID',   text='需求 ID')
        self.tree.heading('状态',     text='状态')
        self.tree.heading('简洁描述', text='简洁描述')
        self.tree.heading('忽略',     text='忽略')
        self.tree.heading('差异摘要', text='差异摘要（点击行查看详情）')
        self.tree.column('需求ID',   width=80,   anchor='center')
        self.tree.column('状态',     width=90,   anchor='center')
        self.tree.column('简洁描述', width=115,  anchor='center')
        self.tree.column('忽略',     width=60,   anchor='center')
        self.tree.column('差异摘要', width=1050, anchor='w')

        self.tree.tag_configure('diff',        background='#fff5f5')
        self.tree.tag_configure('same',        background='#f0fff4')
        self.tree.tag_configure('only_a',      background='#fffde7')
        self.tree.tag_configure('only_b',      background='#e8f4fd')
        self.tree.tag_configure('ignored',     background='#ecf0f1', foreground='#aaa')

        sb = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        # 右键菜单
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label='🚫 标记为忽略',   command=lambda: self._toggle_ignore(True))
        self._ctx_menu.add_command(label='✅ 取消忽略',      command=lambda: self._toggle_ignore(False))
        self.tree.bind('<Button-3>', self._show_ctx)
        # 双击切换忽略
        self.tree.bind('<Double-1>', lambda _: self._toggle_ignore())

    # ── 详情面板 ─────────────────────────────────────
    def _build_detail(self):
        outer = tk.Frame(self, bg='#f0f4f8')
        outer.pack(fill='both', expand=True, padx=12, pady=6)

        # 顶部标签栏 + 操作按钮
        top_bar = tk.Frame(outer, bg='#f0f4f8')
        top_bar.grid(row=0, column=0, columnspan=3, sticky='ew', padx=4, pady=(0,4))
        outer.rowconfigure(1, weight=1); outer.columnconfigure(0, weight=1)

        self.label_bar = tk.Label(top_bar, text='', bg='#f0f4f8',
                                  font=('Microsoft YaHei', 10, 'bold'),
                                  fg='#2c3e50', anchor='w')
        self.label_bar.pack(side='left')
        self.btn_ignore_detail = tk.Button(top_bar, text='🚫 忽略此条',
                                           command=lambda: self._toggle_ignore(True),
                                           bg='#e74c3c', fg='white', relief='flat',
                                           padx=10, pady=2, cursor='hand2',
                                           font=('Microsoft YaHei', 9))
        self.btn_ignore_detail.pack(side='right', padx=4)
        self.btn_unignore_detail = tk.Button(top_bar, text='↩ 取消忽略',
                                             command=lambda: self._toggle_ignore(False),
                                             bg='#27ae60', fg='white', relief='flat',
                                             padx=10, pady=2, cursor='hand2',
                                             font=('Microsoft YaHei', 9))
        self.btn_unignore_detail.pack(side='right', padx=4)

        pane = tk.Frame(outer, bg='#f0f4f8')
        pane.grid(row=1, column=0, columnspan=3, sticky='nsew')

        for col, title, attr, color in [
            (0, 'A 需求内容（差分2E3）',   'txt_a',    '#e8f4fd'),
            (1, 'B 需求内容（差分10327）',  'txt_b',    '#f0fff4'),
            (2, '差异点',                   'txt_diff', '#fff9f0'),
        ]:
            f = tk.LabelFrame(pane, text=title, font=('Microsoft YaHei', 9, 'bold'),
                               bg=color, fg='#2c3e50', relief='solid', bd=1)
            f.grid(row=0, column=col, sticky='nsew', padx=4)
            pane.columnconfigure(col, weight=1)
            pane.rowconfigure(0, weight=1)
            txt = tk.Text(f, wrap='word', font=('Microsoft YaHei', 9),
                          bg=color, relief='flat', state='disabled', padx=6, pady=6)
            sb2 = ttk.Scrollbar(f, command=txt.yview)
            txt.configure(yscrollcommand=sb2.set)
            txt.pack(side='left', fill='both', expand=True)
            sb2.pack(side='right', fill='y')
            txt.tag_configure('add',     foreground='#27ae60', font=('Microsoft YaHei', 9,'bold'))
            txt.tag_configure('remove',  foreground='#e74c3c', font=('Microsoft YaHei', 9,'bold'))
            txt.tag_configure('header',  foreground='#8e44ad', font=('Microsoft YaHei', 9,'bold'))
            txt.tag_configure('ignored', foreground='#aaa',    font=('Microsoft YaHei', 9,'italic'))
            setattr(self, attr, txt)

    # ── 状态栏 ───────────────────────────────────────
    def _build_status(self):
        self.status_var = tk.StringVar(value='请选择两个 XLS 文件后点击「开始对比」')
        tk.Label(self, textvariable=self.status_var, bg='#2c3e50', fg='#bdc3c7',
                 font=('Microsoft YaHei', 9), anchor='w', padx=12, pady=4
                 ).pack(fill='x', side='bottom')

    # ═══════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════
    def _pick(self, var):
        p = filedialog.askopenfilename(
            filetypes=[('Excel 文件', '*.xls *.xlsx'), ('所有文件', '*.*')])
        if p: var.set(p)

    def _run_compare(self):
        a, b = self.file_a.get().strip(), self.file_b.get().strip()
        if not a or not b:
            messagebox.showwarning('提示', '请先选择 A 和 B 两个表格文件')
            return
        self._ignored.clear()
        self.btn_compare.configure(state='disabled', text='⏳ 对比中...')
        self.status_var.set('正在转换文件，请稍候...')
        threading.Thread(target=self._do_compare, args=(a, b), daemon=True).start()

    def _do_compare(self, a, b):
        try:
            self.status_var.set('正在读取 A 文件...')
            d1 = xls_to_dict(a)
            self.status_var.set('正在读取 B 文件...')
            d2 = xls_to_dict(b)
            self.status_var.set('正在对比...')
            results = compare(d1, d2)
            self.after(0, self._load_results, results, a, b)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror('错误', str(e)))
            self.after(0, lambda: self.btn_compare.configure(state='normal', text='▶ 开始对比'))
            self.after(0, lambda: self.status_var.set('对比失败'))

    def _load_results(self, results, a, b):
        self._data = results
        self._apply_filter()
        nd = sum(1 for r in results if r[4]=='diff')
        ns = sum(1 for r in results if r[4]=='same')
        na = sum(1 for r in results if r[4]=='only_a')
        nb = sum(1 for r in results if r[4]=='only_b')
        self.btn_compare.configure(state='normal', text='▶ 开始对比')
        self.status_var.set(
            f'共 {len(results)} 条  |  有差异: {nd}  |  相同: {ns}  '
            f'|  仅A有: {na}  |  仅B有: {nb}'
            f'  ·  A: {os.path.basename(a)}   B: {os.path.basename(b)}'
        )

    def _apply_filter(self):
        mode        = self.filter_var.get()
        search      = self.search_var.get().strip()
        hide_ign    = self.hide_ignored_var.get()
        filtered = [
            r for r in self._data
            if (mode == 'all' or r[4] == mode)
            and (not search or search in r[0])
            and (not hide_ign or r[0] not in self._ignored)
        ]
        self._filtered = filtered
        self.tree.delete(*self.tree.get_children())
        for rid, c1, c2, diff_text, status, label in filtered:
            ignored = rid in self._ignored
            ign_mark = '🚫' if ignored else ''
            summary = diff_text.replace('\n', ' ')[:110] if diff_text else (
                '（内容相同）' if status == 'same' else '')
            tag = 'ignored' if ignored else status
            self.tree.insert('', 'end',
                             values=(rid, STATUS_MAP.get(status, status), label, ign_mark, summary),
                             tags=(tag,))
        n_ign = len(self._ignored)
        self.count_label.configure(
            text=f'显示 {len(filtered)} / {len(self._data)} 条  |  已忽略: {n_ign}')
        self._clear_detail()

    def _on_select(self, _event):
        sel = self.tree.selection()
        if not sel: return
        idx = self.tree.index(sel[0])
        if idx >= len(self._filtered): return
        rid, c1, c2, diff_text, status, label = self._filtered[idx]
        ignored = rid in self._ignored
        color = LABEL_COLOR.get(label, '#636e72')
        badge = f'  🏷  {label}  ' if label else '  —  '
        ign_str = '  🚫 已忽略' if ignored else ''
        self.label_bar.configure(text=f'需求 {rid}    {badge}{ign_str}', fg=color)
        self._set_text(self.txt_a, c1)
        self._set_text(self.txt_b, c2)
        if ignored:
            self._set_ignored_hint(self.txt_diff, label)
        else:
            self._set_diff(self.txt_diff, diff_text)

    def _get_selected_rid(self):
        sel = self.tree.selection()
        if not sel: return None
        idx = self.tree.index(sel[0])
        if idx >= len(self._filtered): return None
        return self._filtered[idx][0]

    def _show_ctx(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._ctx_menu.post(event.x_root, event.y_root)

    def _toggle_ignore(self, force=None):
        rid = self._get_selected_rid()
        if not rid: return
        if force is True:
            self._ignored.add(rid)
        elif force is False:
            self._ignored.discard(rid)
        else:
            if rid in self._ignored: self._ignored.discard(rid)
            else: self._ignored.add(rid)
        self._apply_filter()
        # 重新选中同一行（如果还在列表中）
        for item in self.tree.get_children():
            vals = self.tree.item(item, 'values')
            if vals and vals[0] == rid:
                self.tree.selection_set(item)
                self.tree.see(item)
                self._on_select(None)
                break

    def _auto_ignore(self):
        if not self._data:
            messagebox.showinfo('提示', '请先执行对比')
            return
        before = len(self._ignored)
        for rid, _, _, _, _, label in self._data:
            if label in NON_DIFF_LABELS:
                self._ignored.add(rid)
        added = len(self._ignored) - before
        self._apply_filter()
        messagebox.showinfo('自动忽略完成',
                            f'已自动忽略 {added} 条非实质差异\n'
                            f'（标签为：{" / ".join(NON_DIFF_LABELS)}）')

    def _clear_ignored(self):
        n = len(self._ignored)
        self._ignored.clear()
        self._apply_filter()
        self.status_var.set(f'已取消 {n} 条忽略记录')

    # ── 导出 ────────────────────────────────────────
    def _export(self):
        if not self._data:
            messagebox.showinfo('提示', '请先执行对比')
            return
        choices = ['仅导出当前筛选结果', '导出全部（含已忽略）', '仅导出未忽略的有差异项']
        dlg = ExportDialog(self, choices)
        self.wait_window(dlg)
        if not dlg.result: return
        choice = dlg.result

        if choice == choices[0]:
            rows_data = self._filtered
        elif choice == choices[1]:
            rows_data = self._data
        else:
            rows_data = [r for r in self._data if r[4]=='diff' and r[0] not in self._ignored]

        path = filedialog.asksaveasfilename(
            defaultextension='.xlsx',
            filetypes=[('Excel', '*.xlsx'), ('CSV', '*.csv')],
            initialfile='需求对比结果.xlsx'
        )
        if not path: return

        header = ['需求ID', '状态', '简洁描述', '是否忽略', 'A需求内容(差分2E3)', 'B需求内容(差分10327)', '差异点']
        rows = [header]
        for rid, c1, c2, diff_text, status, label in rows_data:
            ign = '是' if rid in self._ignored else '否'
            rows.append([rid, STATUS_MAP.get(status, status), label, ign, c1, c2, diff_text])

        try:
            if path.endswith('.csv'):
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    csv.writer(f).writerows(rows)
            else:
                export_xlsx(rows, path)
            messagebox.showinfo('导出成功', f'已导出 {len(rows)-1} 条记录\n{path}')
        except Exception as e:
            messagebox.showerror('导出失败', str(e))

    # ── 文本渲染 ─────────────────────────────────────
    def _set_text(self, widget, text):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('end', text)
        widget.configure(state='disabled')

    def _set_diff(self, widget, diff_text):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        in_b = False
        for line in diff_text.splitlines():
            if line == '【A有B无】':
                widget.insert('end', line + '\n', 'header'); in_b = False
            elif line == '【B有A无】':
                widget.insert('end', line + '\n', 'header'); in_b = True
            elif in_b:
                widget.insert('end', line + '\n', 'add')
            else:
                widget.insert('end', line + '\n', 'remove')
        widget.configure(state='disabled')

    def _set_ignored_hint(self, widget, label):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('end', f'\n  ��  此条已标记为忽略\n\n  分类：{label or "—"}\n\n'
                             f'  双击行或点击「取消忽略」恢复查看', 'ignored')
        widget.configure(state='disabled')

    def _clear_detail(self):
        self.label_bar.configure(text='')
        for w in (self.txt_a, self.txt_b, self.txt_diff):
            w.configure(state='normal')
            w.delete('1.0', 'end')
            w.configure(state='disabled')


# ═══════════════════════════════════════════════════════
#  导出选项对话框
# ═══════════════════════════════════════════════════════
class ExportDialog(tk.Toplevel):
    def __init__(self, parent, choices):
        super().__init__(parent)
        self.title('选择导出范围')
        self.resizable(False, False)
        self.result = None
        self.grab_set()
        tk.Label(self, text='请选择导出范围：',
                 font=('Microsoft YaHei', 10, 'bold'), pady=10).pack(padx=20)
        self._var = tk.StringVar(value=choices[0])
        for c in choices:
            tk.Radiobutton(self, text=c, variable=self._var, value=c,
                           font=('Microsoft YaHei', 9), anchor='w').pack(
                fill='x', padx=30, pady=3)
        btn_row = tk.Frame(self); btn_row.pack(pady=12)
        tk.Button(btn_row, text='确定', command=self._ok,
                  bg='#27ae60', fg='white', relief='flat', padx=20, pady=4).pack(side='left', padx=8)
        tk.Button(btn_row, text='取消', command=self.destroy,
                  bg='#e74c3c', fg='white', relief='flat', padx=20, pady=4).pack(side='left', padx=8)
        self.protocol('WM_DELETE_WINDOW', self.destroy)

    def _ok(self):
        self.result = self._var.get()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
