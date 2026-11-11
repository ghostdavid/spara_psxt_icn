"""ICN / ccICN 公式驱动计算的数学验证测试。

验证策略:
1. 默认公式与规范公式的独立参考实现对照
   (sin(pi x)/(pi x) 谱包络, sf 缩放因子, 2*Δf 积分, 信道损耗因子);
2. 公式可修改性: 替换某条公式后计算结果随之变化;
3. 表达式求值器: 科学计数法/四则/幂/函数/常量, 以及安全性
   (拒绝属性访问、未知函数、未知变量、下标等);
4. 端到端: 合成 8 端口 S 参数 -> 功率和 -> ICN (单位 V);
5. 非法输入: 空公式、语法错误、矢量形状不符、非有限结果。

用法: python tests/test_icn.py
"""

import sys
import tempfile
import shutil
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

import sparam_core as core  # noqa: E402
import synth_touchstone as synth  # noqa: E402


def ref_spectrum(fn_hz, fb_hz, amp_v, t_s, pam):
    """默认 Wnt/Wft 公式的独立参考实现 (不经过求值器)。"""
    fb = fb_hz * 1e9
    ft = 0.2365 / t_s
    fr = 1.5 * (fb / 2)
    sf = (pam + 1) / (3 * (pam - 1))
    x = fn_hz / fb
    sinc = np.where(x == 0, 1.0, np.sin(np.pi * x) / (np.pi * x))
    return (sf * (amp_v * amp_v / fb) * sinc ** 2
            / (1.0 + (fn_hz / ft) ** 4)
            / (1.0 + (fn_hz / fr) ** 8))


def ref_loss(fn_hz, fb_hz, il_db):
    return 10.0 ** ((-2.0 * il_db * fn_hz / (fb_hz * 1e9)) / 10.0)


SCALARS = {'Ant': 0.5, 'Aft': 0.4, 'fb': 32e9,
           'Tnt': 7.5e-12, 'Tft': 7.5e-12, 'PAM': 4,
           'ILn': 2 * 8.5, 'ILf': 22.75 + 8.5,
           'fstep': 10e6}


def test_default_formulas_match_reference():
    """默认公式链与独立参考实现逐字对照。"""
    fb_ghz = 32.0
    fn = np.linspace(1e6, 16e9, 1600)          # Hz
    deltaf = SCALARS['fstep']                   # 默认公式 deltaf = fstep
    ps_f = 10.0 ** (-33.0 / 10.0) * np.ones_like(fn)
    ps_n = 10.0 ** (-27.0 / 10.0) * np.ones_like(fn)

    out = core.icn_calculate(fn, ps_f, ps_n, SCALARS)

    w_n = ref_spectrum(fn, fb_ghz, SCALARS['Ant'], SCALARS['Tnt'],
                       SCALARS['PAM'])
    w_f = ref_spectrum(fn, fb_ghz, SCALARS['Aft'], SCALARS['Tft'],
                       SCALARS['PAM'])
    exp_n = float(np.sqrt(2 * deltaf * np.sum(w_n * ps_n)))
    exp_f = float(np.sqrt(2 * deltaf * np.sum(w_f * ps_f)))
    exp_cc_n = float(np.sqrt(2 * deltaf * np.sum(
        w_n * ps_n * ref_loss(fn, fb_ghz, SCALARS['ILn']))))
    exp_cc_f = float(np.sqrt(2 * deltaf * np.sum(
        w_f * ps_f * ref_loss(fn, fb_ghz, SCALARS['ILf']))))

    np.testing.assert_allclose(out['icn_n'], exp_n, rtol=1e-12)
    np.testing.assert_allclose(out['icn_f'], exp_f, rtol=1e-12)
    np.testing.assert_allclose(out['icn'], np.hypot(exp_n, exp_f), rtol=1e-12)
    np.testing.assert_allclose(out['ccicn_n'], exp_cc_n, rtol=1e-12)
    np.testing.assert_allclose(out['ccicn_f'], exp_cc_f, rtol=1e-12)
    np.testing.assert_allclose(out['ccicn'], np.hypot(exp_cc_n, exp_cc_f),
                               rtol=1e-12)
    print('  PASS 默认公式链与独立参考实现一致 (含 sf/PAM 缩放)')


def test_editable_formulas_take_effect():
    """修改公式后计算结果必须随之变化。"""
    fn = np.linspace(1e6, 10e9, 999)
    ones = np.ones_like(fn)

    base = core.icn_calculate(fn, ones, ones, SCALARS)

    # 例1: ICN 合成方式改为线性相加
    f_lin = dict(core.DEFAULT_FORMULAS)
    f_lin['ICN'] = 'ICN_n+ICN_f'
    out_lin = core.icn_calculate(fn, ones, ones, SCALARS, f_lin)
    np.testing.assert_allclose(out_lin['icn'], base['icn_n'] + base['icn_f'],
                               rtol=1e-12)

    # 例2: fr 公式改动 -> 谱形状变化 -> 结果变化
    f_fr = dict(core.DEFAULT_FORMULAS)
    f_fr['fr'] = '10*fb'
    out_fr = core.icn_calculate(fn, ones, ones, SCALARS, f_fr)
    assert not np.isclose(out_fr['icn'], base['icn']), 'fr 改动未生效'

    # 例3: ccICN_n 去掉信道损耗 (ILn=0 时 ChannelLoss_n 全 1)
    f_noloss = dict(core.DEFAULT_FORMULAS)
    f_noloss['ccICN_n'] = 'ICN_n'
    out_nl = core.icn_calculate(fn, ones, ones, SCALARS, f_noloss)
    np.testing.assert_allclose(out_nl['ccicn_n'], base['icn_n'], rtol=1e-12)

    # 例4: deltaf 公式化 —— 改为 2*fstep 后 ICN 各项变为 sqrt(2) 倍
    f_df = dict(core.DEFAULT_FORMULAS)
    f_df['deltaf'] = '2*fstep'
    out_df = core.icn_calculate(fn, ones, ones, SCALARS, f_df)
    np.testing.assert_allclose(out_df['icn'], base['icn'] * np.sqrt(2),
                               rtol=1e-12)
    np.testing.assert_allclose(out_df['ccicn'], base['ccicn'] * np.sqrt(2),
                               rtol=1e-12)
    print('  PASS 公式修改后计算沿用新公式 (含 deltaf 公式化)')


def test_evaluator():
    """表达式求值器: 功能与安全性。"""
    e = core.evaluate_expr
    np.testing.assert_allclose(e('32e9'), 32e9)
    np.testing.assert_allclose(e('7.5e-12'), 7.5e-12)
    np.testing.assert_allclose(e('2*8.5'), 17.0)
    np.testing.assert_allclose(e('22.75+8.5'), 31.25)
    np.testing.assert_allclose(e('pow(2,10)'), 1024.0)
    np.testing.assert_allclose(e('2**10'), 1024.0)
    np.testing.assert_allclose(e('sin(pi/2)'), 1.0)
    np.testing.assert_allclose(e('sqrt(2)*sqrt(2)'), 2.0)
    np.testing.assert_allclose(e('(1+2)*3/4-1'), 1.25)
    np.testing.assert_allclose(e('-abs(-3)'), -3.0)
    np.testing.assert_allclose(e('log10(100)+e*0'), 2.0)

    fn = np.array([1.0, 2.0, 3.0])
    np.testing.assert_allclose(e('sum(fn*2)', {'fn': fn}), 12.0)

    for bad in ('', '1+', 'foo(1)', 'foo', '__import__("os")',
                'os.system("dir")', '[1,2][0]', 'a.b', 'lambda: 1',
                '"str"', 'True'):
        try:
            e(bad, {'a': np.array([1.0])})
        except ValueError:
            continue
        raise AssertionError(f'危险/非法表达式未拦截: {bad!r}')
    print('  PASS 求值器功能正确且拒绝越界构造')


def test_end_to_end_power_sum():
    """合成 8 端口 S 参数 -> 功率和 -> ICN 完整链路 (单位 V)。"""
    tmp = Path(tempfile.mkdtemp(prefix='icn_test_'))
    try:
        path = synth.write_case(tmp, 'icn8.s8p', 8, fmt='RI', num_freqs=101)
        sp = core.SParameter(str(path))
        result = core.power_sum_db(sp, 50.0, [1, 2], [5, 6, 7, 8], [3, 4],
                                   True, 0.5, 5.0)
        # fstep 取功率和网格的实际间隔, 使默认公式 deltaf=fstep 与网格一致
        scalars = dict(SCALARS, fstep=result['deltaf_hz'])
        out = core.icn_calculate(result['fn_hz'],
                                 result['fext_power_lin'],
                                 result['next_power_lin'],
                                 scalars)
        for key in ('icn', 'icn_f', 'icn_n', 'ccicn', 'ccicn_f', 'ccicn_n'):
            assert np.isfinite(out[key]) and out[key] > 0, f'{key} 非正数'
        assert out['ccicn'] < out['icn'], 'IL>0 时 ccICN 应小于 ICN'
        # fn_hz 与 fn_ghz 一致性
        np.testing.assert_allclose(result['fn_hz'],
                                   result['fn_ghz'] * 1e9, rtol=1e-12)
        print(f"  PASS 端到端链路 (ICN={out['icn']:.6g} V, "
              f"ccICN={out['ccicn']:.6g} V)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_invalid_formulas():
    fn = np.linspace(1e6, 10e9, 99)
    ones = np.ones_like(fn)

    cases = [
        ({'fr': ''}, '空公式'),
        ({'fr': '1+'}, '语法错误'),
        ({'Wnt': '1.0'}, '矢量形状不符'),
        ({'Wnt': 'fn/0'}, '非有限结果'),
        ({'sf': 'fn'}, '标量中间量收到矢量'),
        ({'ICN': 'fn'}, '结果非标量'),
        ({'deltaf': '0'}, 'deltaf 为 0'),
        ({'deltaf': '-fstep'}, 'deltaf 为负'),
    ]
    for override, label in cases:
        formulas = dict(core.DEFAULT_FORMULAS, **override)
        try:
            core.icn_calculate(fn, ones, ones, SCALARS, formulas)
        except ValueError:
            continue
        raise AssertionError(f'非法公式 ({label}) 未抛 ValueError')
    print('  PASS 非法公式 (空/语法/形状/非有限/deltaf非正) 均抛 ValueError')


def main():
    print('运行 ICN / ccICN 公式驱动计算验证测试...')
    test_default_formulas_match_reference()
    test_editable_formulas_take_effect()
    test_evaluator()
    test_end_to_end_power_sum()
    test_invalid_formulas()
    print('全部 ICN 测试通过 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
