"""S参数解析与 PowerSum 计算的回归测试。

对比两种基线:
1. 旧版快照 (tests/snapshot_v3.3.json, 由重构前的 main.py 生成):
   除白名单中"已知修复"的用例外, 新实现输出必须与旧版一致;
2. 解析解 (由 tests/synth_touchstone.py 的确定性公式直接推得):
   验证白名单用例的修复结果以及数学工具函数的正确性。

用法: python tests/test_sparam.py
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

SNAPSHOT_FILE = HERE / 'snapshot_v3.3.json'

# 旧版存在 bug、新版已修复的用例: 跳过快照对比, 改为解析解断言
# s2p_ri_rep9: F=9 时 90 个值同时被 standard(9)/repeated(10) 整除,
# 旧版无条件按 standard 解析出垃圾矩阵 (快照里的负频率即是证据)
EXPECTED_FIX_CASES = {'s2p_ri_rep2', 's2p_ri_rep9', 'noext_ri_4port'}

RTOL = 1e-8
ATOL = 1e-9


def assert_close(actual, expected, msg):
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL,
                               err_msg=msg)


def c2l(arr):
    arr = np.asarray(arr)
    return np.stack([arr.real, arr.imag], axis=-1)


# -------------------- 快照对比 --------------------

def test_parse_matches_old_snapshot(cases, snap):
    for name, data in snap['parse'].items():
        if name in EXPECTED_FIX_CASES:
            continue
        sp = core.SParameter(str(cases[name]))
        assert sp.num_ports == data['num_ports'], f'{name}: num_ports 不一致'
        np.testing.assert_allclose(sp.z0, data['z0'], rtol=0, atol=0)
        assert list(sp.port_names) == data['port_names'], f'{name}: 端口名不一致'
        assert_close(sp.frequencies, np.asarray(data['frequencies']),
                     f'{name}: 频率与旧版不一致')
        assert_close(c2l(sp.parameters), np.asarray(data['parameters']),
                     f'{name}: S参数与旧版不一致')
    print(f'  PASS 解析结果与旧版快照一致 '
          f'({len(snap["parse"]) - len(EXPECTED_FIX_CASES)} 个用例)')


def test_math_matches_old_snapshot(cases, snap):
    sp8 = core.SParameter(str(cases['s8p_ri_z0_75']))

    renorm = core.snp2smp(sp8.parameters, 75.0, [1, 2, 5, 6], 50.0)
    reorder = core.snp2smp(sp8.parameters, 75.0, [1, 2, 5, 6], 75.0)
    sdd = core.s2sdd(renorm)
    assert_close(c2l(renorm), np.asarray(snap['math']['snp2smp_renorm']),
                 'snp2smp 阻抗归一化与旧版不一致')
    assert_close(c2l(reorder), np.asarray(snap['math']['snp2smp_reorder']),
                 'snp2smp 端口重排与旧版不一致')
    assert_close(c2l(sdd), np.asarray(snap['math']['s2sdd_renorm']),
                 's2sdd 与旧版不一致')
    # 功率曲线不再做快照对比: 旧版快照基于插值网格, V3.5 起移除插值,
    # 计算直接在原始频点上进行, 两套网格无可比性;
    # 功率和正确性由 test_native_grid_fidelity 等解析解断言覆盖
    print('  PASS snp2smp / s2sdd 与旧版快照一致')


def test_native_grid_fidelity(cases):
    """移除插值后: 结果频点必须是原始文件频点的子集, 且数值等于逐点手算。"""
    sp8 = core.SParameter(str(cases['s8p_ri_z0_75']))
    result = core.power_sum_db(sp8, 50.0, [1, 2], [5, 6, 7, 8], [3, 4],
                               True, 0.2, 0.8)

    # 频点 = 原始频点落在 [fmin, fmax] 内的子集, 不多不少
    freqs_ghz = sp8.frequencies / 1e9
    expected_fn = freqs_ghz[(freqs_ghz >= 0.2) & (freqs_ghz <= 0.8)]
    assert_close(result['fn_ghz'], expected_fn, '结果频点不是原始频点子集')
    # deltaf = 原始频点间隔 (合成文件均匀 0.1 GHz)
    assert_close(np.asarray(result['deltaf_hz']),
                 np.asarray(0.1e9), 'deltaf 不等于原始频点间隔')

    # 逐点手算 PSNEXT: 与实现口径一致 —— 先把全 8 端口矩阵归一化到
    # 目标 z0 (保留其余端口的终端耦合效应), 再抽取受害对+攻击对
    # 4 端口子矩阵做混合模转换, 取攻击对输入到受害对输出的 Sdd12
    full = core.snp2smp(sp8.parameters, 75.0, list(range(1, 9)), 50.0)
    sdd = core.s2sdd(core.snp2smp(full, 50.0, [1, 2, 3, 4], 50.0))
    mask = (freqs_ghz >= 0.2) & (freqs_ghz <= 0.8)
    expected_next = 20 * np.log10(np.abs(sdd[0, 1, mask]))
    assert_close(np.asarray(result['MDNEXT']), expected_next,
                 'PSNEXT 与逐点手算不一致')
    print('  PASS 移除插值后结果频点忠于原始数据且与逐点手算一致')


def test_resample_sparams(cases):
    """重采样预处理: 网格正确、节点还原、加密、平坦延拓、不污染原数据。

    合成文件网格均匀: 0.1 GHz 起步, 步长 0.1 GHz, 共 11 点 (z0=75)。
    """
    sp8 = core.SParameter(str(cases['s8p_ri_z0_75']))
    orig_params = sp8.parameters.copy()
    orig_freqs = sp8.frequencies.copy()

    # 1) 与原始网格同参数重采样: 频点一致, 节点值 = 归一化后的原始值
    params, freqs = core.resample_sparams(sp8, 50.0, 0.1, 1.1, 0.1)
    assert_close(freqs, orig_freqs, '重采样网格与原始频点不一致')
    expected = core.snp2smp(orig_params, 75.0, list(range(1, 9)), 50.0)
    assert_close(c2l(params), c2l(expected), '节点处重采样值不等于归一化原值')

    # 2) z0 相同则不做归一化: 节点值 = 原始值
    params75, _ = core.resample_sparams(sp8, 75.0, 0.1, 1.1, 0.1)
    assert_close(c2l(params75), c2l(orig_params), 'z0 相同时不应改变数值')

    # 3) 加密网格 (步长减半): 偶数点仍落在原节点上且值不变
    params_fine, freqs_fine = core.resample_sparams(sp8, 75.0, 0.1, 1.1, 0.05)
    assert freqs_fine.shape == (21,), f'加密网格点数错误: {freqs_fine.shape}'
    assert_close(c2l(params_fine[:, :, ::2]), c2l(orig_params),
                 '加密网格节点处值不等于原值')

    # 4) 量程外平坦延拓: 超出文件范围的频点取边界值
    params_ext, freqs_ext = core.resample_sparams(sp8, 75.0, 0.05, 1.15, 0.05)
    assert_close(np.asarray(freqs_ext[0]), np.asarray(0.05e9),
                 '延拓网格起点错误')
    assert_close(np.asarray(freqs_ext[-1]), np.asarray(1.15e9),
                 '延拓网格终点错误')
    assert_close(c2l(params_ext[:, :, 0]), c2l(orig_params[:, :, 0]),
                 '下边界外未平坦延拓到首频点值')
    assert_close(c2l(params_ext[:, :, -1]), c2l(orig_params[:, :, -1]),
                 '上边界外未平坦延拓到末频点值')

    # 5) 原始数据不被修改 (阻抗归一化/插值均产生新数组)
    assert_close(c2l(sp8.parameters), c2l(orig_params),
                 'resample_sparams 污染了原始 S 参数')
    assert_close(sp8.frequencies, orig_freqs,
                 'resample_sparams 污染了原始频率轴')
    print('  PASS 重采样预处理: 节点还原/加密/平坦延拓/原数据不污染')


def test_editable_power_formulas(cases):
    """PSNEXT/PSFEXT/PSXT 直接使用 RAW 数据, 且公式修改后生效。"""
    assert 'FEXT_dB' not in core.DEFAULT_FORMULAS
    assert 'NEXT_dB' not in core.DEFAULT_FORMULAS
    assert len(core.DEFAULT_FORMULAS) == 18
    sp8 = core.SParameter(str(cases['s8p_ri_z0_75']))
    base = core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                             True, 0.1, 1.1)

    # 例1: PSNEXT 功率减半, 验证 RAW 公式链路生效
    f_half = {'PSNEXT': '10*log10(psum(pow(10,RAW_NEXT_dB/10))/2)'}
    out_half = core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                                 True, 0.1, 1.1, formulas=f_half)
    assert_close(np.asarray(out_half['MDNEXT']),
                 np.asarray(base['MDNEXT']) - 10 * np.log10(2),
                 'PSNEXT 公式修改 (功率减半) 未生效')

    # 例2: 直接在 PSNEXT 公式中把 RAW_NEXT_dB 加 6 dB
    f_plus6 = {'PSNEXT': '10*log10(psum(pow(10,(RAW_NEXT_dB+6)/10)))'}
    out_plus6 = core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                                  True, 0.1, 1.1, formulas=f_plus6)
    assert_close(np.asarray(out_plus6['MDNEXT']),
                 np.asarray(base['MDNEXT']) + 6.0,
                 'PSNEXT 公式修改 (+6dB) 未生效')

    # 例3: 已移除的 NEXT_dB 映射名称不再存在
    try:
        core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                          True, 0.1, 1.1,
                          formulas={'PSNEXT': '10*log10(psum(pow(10,NEXT_dB/10)))'})
    except ValueError:
        pass
    else:
        raise AssertionError('已移除的 NEXT_dB 名称仍可使用')

    # 例4: PSXT 公式可引用 PSFEXT/PSNEXT (改为只取 NEXT)
    f_xt = {'PSXT': 'PSNEXT'}
    out_xt = core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                               True, 0.1, 1.1, formulas=f_xt)
    assert_close(np.asarray(out_xt['PSXT']), np.asarray(out_xt['MDNEXT']),
                 'PSXT 公式引用 PSNEXT 未生效')

    # 例5: 非法公式 (形状不符) 抛 ValueError
    try:
        core.power_sum_db(sp8, 50.0, [1, 2], [5, 6], [3, 4],
                          True, 0.1, 1.1, formulas={'PSNEXT': '1.0'})
    except ValueError:
        pass
    else:
        raise AssertionError('形状不符的 PSNEXT 公式未抛 ValueError')
    print('  PASS RAW_FEXT_dB/RAW_NEXT_dB/PSFEXT/PSNEXT/PSXT 公式正确且生效')


# -------------------- 修复用例的解析解断言 --------------------

def test_fixed_2port_repeated_format(cases):
    """旧版把 2 端口 repeated 格式按 standard 误读, 新版正确解析。

    覆盖两种触发路径: rep2 (仅 repeated 整除) 与 rep9 (standard/repeated
    同时整除的布局歧义, 需按频率单调性消歧)。
    """
    for name, num_freqs in (('s2p_ri_rep2', 2), ('s2p_ri_rep9', 9)):
        sp = core.SParameter(str(cases[name]))
        assert sp.num_ports == 2
        expected_freqs = np.array([1e8 + 1e8 * k for k in range(num_freqs)])
        assert_close(sp.frequencies, expected_freqs, f'{name} 频率错误')
        for f_idx in range(num_freqs):
            expected = np.asarray(synth.gen_matrix(2, 0.1 * (f_idx + 1)))
            assert_close(sp.parameters[:, :, f_idx], expected,
                         f'{name} S 参数错误 (freq #{f_idx})')
    print('  PASS 修复: 2 端口 repeated-frequency 格式正确解析 '
          '(含布局歧义消歧)')


def test_fixed_port_count_inference(cases):
    """旧版对无后缀文件总会误判为 1 端口, 新版按频率单调性选优。"""
    sp = core.SParameter(str(cases['noext_ri_4port']))
    assert sp.num_ports == 4, f'应推断为 4 端口, 实际 {sp.num_ports}'
    assert list(sp.port_names) == [f'DDR0_DQ{k}' for k in range(4)]
    expected_freqs = np.array([1e8 + 1e8 * k for k in range(11)])
    assert_close(sp.frequencies, expected_freqs, '无后缀文件频率错误')
    for f_idx, f_ghz in enumerate([0.1 + 0.1 * k for k in range(11)]):
        expected = np.asarray(synth.gen_matrix(4, f_ghz))
        assert_close(sp.parameters[:, :, f_idx], expected,
                     f'无后缀文件 S 参数错误 (freq #{f_idx})')
    print('  PASS 修复: 无 .sNp 后缀文件端口数推断正确 (4 端口)')


def test_standard_layout_wins_ambiguity(cases):
    """standard 2 端口 F=10 (90 值) 同时被两种布局整除时仍应判为 standard。"""
    sp = core.SParameter(str(cases['s2p_ri_std10']))
    assert sp.num_ports == 2
    expected_freqs = np.array([1e8 + 1e8 * k for k in range(10)])
    assert_close(sp.frequencies, expected_freqs, 'standard F=10 频率错误')
    for f_idx in range(10):
        expected = np.asarray(synth.gen_matrix(2, 0.1 * (f_idx + 1)))
        assert_close(sp.parameters[:, :, f_idx], expected,
                     f'standard F=10 S 参数错误 (freq #{f_idx})')
    print('  PASS 消歧: standard 布局在两种布局可整除时仍被正确识别')


def test_port_count_inference_rejects_garbage(tmp):
    """无任何单调频率候选时应报错而非误判。"""
    garbage = tmp / 'garbage.dat'
    garbage.write_text('# GHZ S RI R 50\n' + ('5 5 5 5 5 5 5 5 5\n' * 10),
                       encoding='ascii')
    try:
        core.SParameter(str(garbage))
    except ValueError as e:
        assert '端口数量' in str(e)
    else:
        raise AssertionError('垃圾数据应抛出"无法确定端口数量"')
    print('  PASS 无候选布局时给出明确错误')


# -------------------- 数学工具解析解断言 --------------------

def test_s2sdd_formula():
    n, m, num_freqs = 4, 2, 3
    s = (np.arange(n * n * num_freqs).reshape(n, n, num_freqs)
         + 1j * np.arange(n * n * num_freqs).reshape(n, n, num_freqs)[::-1])
    sdd = core.s2sdd(s)
    for i in range(m):
        for j in range(m):
            expected = 0.5 * (s[2 * i, 2 * j, :] - s[2 * i, 2 * j + 1, :]
                              - s[2 * i + 1, 2 * j, :] + s[2 * i + 1, 2 * j + 1, :])
            assert_close(sdd[i, j, :], expected, f's2sdd 公式错误 [{i},{j}]')
    print('  PASS s2sdd 混合模转换公式正确')


def test_snp2smp_renorm_formula():
    rng = np.random.default_rng(42)
    s = (rng.uniform(-0.5, 0.5, (2, 2, 5))
         + 1j * rng.uniform(-0.5, 0.5, (2, 2, 5)))
    out = core.snp2smp(s, 50.0, [1, 2], 75.0)
    gamma = (75.0 - 50.0) / (75.0 + 50.0)
    eye = np.eye(2)
    for f in range(5):
        S = s[:, :, f]
        expected = (S - gamma * eye) @ np.linalg.inv(eye - gamma * S)
        assert_close(out[:, :, f], expected, 'snp2smp 归一化公式错误')
    # 端口重排与 z0 不变时应原样返回
    s3 = rng.uniform(-0.5, 0.5, (3, 3, 2)) + 0j
    reordered = core.snp2smp(s3, 50.0, [3, 1], 50.0)
    assert_close(reordered, s3[[2, 0]][:, [2, 0]], 'snp2smp 重排错误')
    print('  PASS snp2smp 归一化与端口重排正确')


def test_safe_db():
    assert np.isneginf(core.safe_db(np.array([0.0]))[0])
    assert_close(core.safe_db(np.array([0.1])), np.array([20 * np.log10(0.1)]),
                 'safe_db 错误')
    print('  PASS safe_db 兜底逻辑正确')


# -------------------- 原始数据防污染 / 差分配对 --------------------

def test_original_data_not_polluted(cases):
    """power_sum_db 做任何阻抗归一化后, 原始 S 参数必须逐位不变。"""
    sp = core.SParameter(str(cases['s8p_ri_z0_75']))
    params_copy = sp.parameters.copy()
    freqs_copy = sp.frequencies.copy()

    # z0 与文件不同 (触发全矩阵归一化), 差分与单端各算一次
    core.power_sum_db(sp, 50.0, [1, 2], [5, 6, 7, 8], [3, 4], True,
                      0.05, 1.15)
    core.power_sum_db(sp, 50.0, [1], [5, 6], [7, 8], False,
                      0.05, 1.15)
    # 再用与文件相同的 z0 算一次 (走另一条分支)
    core.power_sum_db(sp, 75.0, [1, 2], [5, 6], [3, 4], True,
                      0.05, 1.15)

    np.testing.assert_array_equal(sp.parameters, params_copy,
                                  err_msg='spara.parameters 被计算过程污染')
    np.testing.assert_array_equal(sp.frequencies, freqs_copy,
                                  err_msg='spara.frequencies 被计算过程污染')
    assert sp.z0 == 75.0, 'spara.z0 被修改'
    print('  PASS 阻抗归一化不污染原始 S 参数数据')


def test_diff_pair_helpers():
    """差分对子纯函数: 配对划分、对子相邻重排、半对检测。"""
    # Type1: 连续编号对子 (1,2) (3,4) ...
    assert core.diff_pair(1, 8, 'Type1') == (1, 2)
    assert core.diff_pair(4, 8, 'Type1') == (3, 4)
    # Type2: 奇偶交错对子 (1,3) (2,4) (5,7) (6,8)
    assert core.diff_pair(1, 8, 'Type2') == (1, 3)
    assert core.diff_pair(3, 8, 'Type2') == (1, 3)
    assert core.diff_pair(2, 8, 'Type2') == (2, 4)
    assert core.diff_pair(6, 8, 'Type2') == (6, 8)
    assert core.diff_pair(7, 8, 'Type2') == (5, 7)

    # Type2 下交错勾选的 [1,2,3,4] 必须重排为对子相邻的 [1,3,2,4],
    # 否则 power_sum_db 会错配成 (1,2)/(3,4)
    assert core.order_ports_by_pairs([1, 2, 3, 4], 8, 'Type2') == [1, 3, 2, 4]
    # Type1 下升序列表顺序不变 (向后兼容旧行为)
    assert core.order_ports_by_pairs([1, 2, 3, 4], 8, 'Type1') == [1, 2, 3, 4]
    # 乱序勾选也收敛到对子相邻
    assert core.order_ports_by_pairs([7, 5, 3, 1], 8, 'Type2') == [1, 3, 5, 7]

    # 半对检测: (1,4) 总数为偶数但两个都是半对
    assert core.find_broken_pairs([1, 4], 8, 'Type1') == [1, 4]
    assert core.find_broken_pairs([1, 2], 8, 'Type1') == []
    assert core.find_broken_pairs([1, 3, 2], 8, 'Type2') == [2]
    print('  PASS 差分对子划分/重排/半对检测正确')


def test_diff_pairing_changes_result(cases):
    """同一组 4 个攻击端口, 配对方式不同则 PSNEXT 不同 (证明配对敏感)。"""
    sp = core.SParameter(str(cases['s8p_ri_z0_75']))
    # 攻击端口 3,4,5,6: 正确配对 (3,4)/(5,6) vs 错配 (3,5)/(4,6)
    ok = core.power_sum_db(sp, 50.0, [1, 2], [], [3, 4, 5, 6], True,
                           0.05, 1.15)
    bad = core.power_sum_db(sp, 50.0, [1, 2], [], [3, 5, 4, 6], True,
                            0.05, 1.15)
    assert not np.allclose(ok['MDNEXT'], bad['MDNEXT'], atol=1e-6), \
        '配对变化未影响结果, 测试数据无法区分配对方式'
    print('  PASS 配对方式改变确实改变 PSNEXT (配对敏感性成立)')


# -------------------- 主入口 --------------------

def main():
    snap = None
    if SNAPSHOT_FILE.exists():
        import json
        snap = json.loads(SNAPSHOT_FILE.read_text(encoding='utf-8'))

    tmp = Path(tempfile.mkdtemp(prefix='snp_test_'))
    try:
        cases = synth.generate_all(tmp)
        print('运行回归测试...')
        if snap:
            test_parse_matches_old_snapshot(cases, snap)
            test_math_matches_old_snapshot(cases, snap)
        else:
            print('  SKIP 未找到快照文件, 仅运行解析解断言')
        test_fixed_2port_repeated_format(cases)
        test_standard_layout_wins_ambiguity(cases)
        test_fixed_port_count_inference(cases)
        test_port_count_inference_rejects_garbage(tmp)
        test_s2sdd_formula()
        test_snp2smp_renorm_formula()
        test_safe_db()
        test_native_grid_fidelity(cases)
        test_resample_sparams(cases)
        test_editable_power_formulas(cases)
        test_original_data_not_polluted(cases)
        test_diff_pair_helpers()
        test_diff_pairing_changes_result(cases)
        print('全部测试通过 ✓')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
