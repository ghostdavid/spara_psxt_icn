"""S参数端口格式识别模块 (独立维护, 识别算法集中在本文件, 便于后续修改)。

==================== 如何修改识别算法 ====================
全部识别规则集中在下方 FORMAT_RULES 列表, 每种格式一条:
- key       : 内部标识 (配置文件/代码引用用, 不要改名字符串以外的部分)
- name      : 界面显示名
- pattern   : 端口注释行的匹配正则 (整行含 '!' 前缀),
              第 1 组 = 端口号 (numbering='explicit' 时),
              第 2 组 = 端口名
- numbering : 'explicit' = 端口号取自正则第 1 组;
              'seq'      = 端口号按注释行出现顺序编号
              (Cadence 端口名中的数字不代表矩阵序号)

自动识别逻辑 (detect_port_format): 统计每条规则命中的注释行数,
取命中数最多的规则; 并列时按 FORMAT_RULES 顺序取前者;
全部未命中 (文件无端口注释) 时回退 'generic' (通用格式)。

新增/修改格式时只需调整 FORMAT_RULES, 无需改动其他代码。
==========================================================

当前规则 (基于已有样本文件归纳, 可按实际文件修订):
- cadence : Cadence (Sigrity/Clarity):   ! Port1_DIE_sbump_12052::DDR0_A0D0_DQ0
            (Port 与数字间无空格, 数字后紧跟下划线)
- ansys   : Ansys (HFSS/SIwave/Q3D):     ! Port[1] = name  或  ! Port (1) = name
            (端口号带方括号/圆括号)
- ads     : Keysight ADS:                ! Port 1 = name
            (Port 与数字间有空格, 数字不带括号)
- generic : 通用格式:                     ! 1: name  或  ! 1 = name
            (无 Port 前缀; 也是无端口注释时的兜底格式)
"""

import re

# -------------------- 识别规则表 (修改识别算法只动这里) --------------------

FORMAT_RULES = [
    {
        'key': 'cadence',
        'name': 'Cadence格式',
        'pattern': re.compile(r'!\s*[Pp]ort(\d+)_(.+)'),
        'numbering': 'seq',
    },
    {
        'key': 'ansys',
        'name': 'Ansys格式',
        'pattern': re.compile(
            r'!\s*[Pp]ort\s*[\[\(]\s*(\d+)\s*[\]\)]\s*[:=]\s*(.+)'),
        'numbering': 'explicit',
    },
    {
        'key': 'ads',
        'name': 'ADS格式',
        'pattern': re.compile(r'!\s*[Pp]ort\s+(\d+)\s*[:=]\s*(.+)'),
        'numbering': 'explicit',
    },
    {
        'key': 'generic',
        'name': '通用格式',
        'pattern': re.compile(r'!\s*(\d+)\s*[:=]\s*(.+)'),
        'numbering': 'explicit',
    },
]

FORMAT_KEYS = [rule['key'] for rule in FORMAT_RULES]
FORMAT_NAMES = {rule['key']: rule['name'] for rule in FORMAT_RULES}
DEFAULT_FORMAT = 'generic'


def _rule(key):
    for rule in FORMAT_RULES:
        if rule['key'] == key:
            return rule
    raise ValueError(f'未知端口格式: {key!r} (可选: {FORMAT_KEYS})')


def detect_port_format(comment_lines):
    """自动识别端口格式: 返回命中注释行数最多的格式 key。

    comment_lines: 以 '!' 开头的原始注释行 (建议只传端口注释区段,
    如 TouchstoneFormatFlag 标记之前的部分); 全部规则未命中时
    返回 'generic'。
    """
    best_key, best_hits = DEFAULT_FORMAT, 0
    for rule in FORMAT_RULES:
        hits = sum(1 for line in comment_lines if rule['pattern'].match(line))
        if hits > best_hits:
            best_key, best_hits = rule['key'], hits
    return best_key


def extract_port_names(comment_lines, fmt=DEFAULT_FORMAT):
    """按指定格式从注释行提取端口名, 返回 [(端口号, 端口名)] (按出现顺序)。

    fmt 为 FORMAT_KEYS 之一; 'seq' 编号格式忽略注释中的数字,
    按出现顺序编号 (Cadence 语义)。
    """
    rule = _rule(fmt)
    pattern = rule['pattern']
    names = []
    for line in comment_lines:
        m = pattern.match(line)
        if not m:
            continue
        pname = m.group(2).strip()
        if not pname:
            continue
        if rule['numbering'] == 'seq':
            names.append((len(names) + 1, pname))
        else:
            names.append((int(m.group(1)), pname))
    return names


def detect_and_extract(comment_lines):
    """自动识别并提取: 返回 (格式 key, [(端口号, 端口名)])。"""
    fmt = detect_port_format(comment_lines)
    return fmt, extract_port_names(comment_lines, fmt)
