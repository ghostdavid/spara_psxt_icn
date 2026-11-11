# port_format 端口格式识别模块单元测试
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import port_format as pf

FAILS = []


def check(name, cond):
    print(('  PASS ' if cond else '  FAIL ') + name)
    if not cond:
        FAILS.append(name)


cadence_lines = [
    '! Port103_DIE_sbump_12052::DDR0_A0D0_DQ0',
    '! Port7_DIE_sbump_12053::DDR0_A0D0_DQ1',
]
ansys_lines = ['! Port[1] = TX0_P', '! Port [2] = TX0_N']
ansys_paren = ['! Port (1) : RX0']
ads_lines = ['! Port 1 = DDR0_DQ0', '! Port 2 = DDR0_DQ1']
generic_lines = ['! 1: net_a', '! 2 = net_b']
no_port_lines = ['! some random comment', '! another']

# ---- 自动识别 ----
check('Cadence 注释识别为 cadence',
      pf.detect_port_format(cadence_lines) == 'cadence')
check('Port[1] 方括号识别为 ansys',
      pf.detect_port_format(ansys_lines) == 'ansys')
check('Port (1) 圆括号识别为 ansys',
      pf.detect_port_format(ansys_paren) == 'ansys')
check('Port 1 = 空格识别为 ads',
      pf.detect_port_format(ads_lines) == 'ads')
check('1: name 识别为 generic',
      pf.detect_port_format(generic_lines) == 'generic')
check('无端口注释回退 generic',
      pf.detect_port_format(no_port_lines) == 'generic')

# ---- 端口名提取 ----
check('cadence 按出现顺序编号 (忽略名字中的数字)',
      pf.extract_port_names(cadence_lines, 'cadence')
      == [(1, 'DIE_sbump_12052::DDR0_A0D0_DQ0'),
          (2, 'DIE_sbump_12053::DDR0_A0D0_DQ1')])
check('ansys 取显式端口号',
      pf.extract_port_names(ansys_lines, 'ansys')
      == [(1, 'TX0_P'), (2, 'TX0_N')])
check('ads 提取端口名',
      pf.extract_port_names(ads_lines, 'ads')
      == [(1, 'DDR0_DQ0'), (2, 'DDR0_DQ1')])
check('generic 冒号/等号均可',
      pf.extract_port_names(generic_lines, 'generic')
      == [(1, 'net_a'), (2, 'net_b')])
check('格式互不串扰: ads 行不匹配 cadence 规则',
      pf.extract_port_names(ads_lines, 'cadence') == [])

# ---- 解析器集成 (指定格式 vs 自动) ----
from sparam_core import SParameter

s = SParameter(str(Path(__file__).resolve().parent.parent
                   / 'sample_data' / 'demo.s8p'))
check('demo.s8p 自动识别 (Port 1 = 风格 -> ads)', s.port_format == 'ads')
check('demo.s8p 端口名正确', s.port_names[0] == 'DDR0_DQ0'
      and len(s.port_names) == 8)
s2 = SParameter(str(Path(__file__).resolve().parent.parent
                    / 'sample_data' / 'demo.s8p'), port_format='generic')
check('手动指定 generic 后无端口名', all(n == '-' for n in s2.port_names))
check('手动指定回填实际使用格式', s2.port_format == 'generic')

print('PORT_FORMAT ALL PASS' if not FAILS else f'FAILURES: {FAILS}')
sys.exit(1 if FAILS else 0)
