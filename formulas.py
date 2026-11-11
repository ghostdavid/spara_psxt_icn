"""串扰与 ICN 计算公式（唯一维护入口）。

使用者只需检查、修改本文件中的 DEFAULT_FORMULAS。
保存修改并重新启动软件后，新公式会直接参与实际计算；
主界面和配置文件均不会显示、保存或覆盖这里的公式。

修改方法
--------
1. 找到下方需要调整的公式名，例如 'ICN'。
2. 只修改冒号后引号内的数学表达式，保留公式名、引号和逗号。
3. 保存文件并重新启动软件。表达式有误时，软件会在状态栏报告计算错误。

表达式写法
----------
- 四则运算与乘方：+  -  *  /  **，例如 Ant**2 或 pow(Ant,2)。
- 可用函数：sin、cos、tan、asin、acos、atan、sqrt、exp、log、log10、
  abs、pow、sum、min、max；功率和公式还可用 psum（沿攻击路径求和）。
- 可用常量：pi、e。
- 数值支持科学计数法，例如 32e9、7.5e-12。

公式按以下顺序求值，后面的公式可以引用前面已经得到的结果：
1. PSFEXT -> PSNEXT -> PSXT；
2. deltaf -> fr -> ft_n -> ft_f -> sf；
3. Wnt -> Wft -> ChannelLoss_n -> ChannelLoss_f；
4. ICN_n -> ICN_f -> ICN -> ccICN_n -> ccICN_f -> ccICN。

可用变量
--------
串扰公式环境：
- RAW_FEXT_dB、RAW_NEXT_dB：从 S 参数直接提取的原始耦合矩阵，
  每行是一条攻击路径，每列是一个频点，单位为 dB。
- PSFEXT、PSNEXT、PSXT：每个频点一个数值的功率和曲线，单位为 dB。

ICN 公式环境：
- Ant、Aft：近端、远端攻击幅度（V，mean-pk）。
- fb：波特率（Hz）；Tnt、Tft：上升时间（s）；PAM：电平数。
- ILn、ILf：近端、远端路径损耗（dB）。
- fstep：频率步长（Hz）；deltaf：积分步长（Hz），默认等于 fstep。
- fn：频率数组（Hz）；PSNEXT、PSFEXT：对应功率和曲线（dB）。
- Wnt、Wft：攻击信号频谱权重；ChannelLoss_n、ChannelLoss_f：信道损耗因子。
- ICN_n、ICN_f、ICN、ccICN_n、ccICN_f、ccICN：最终结果（V）。

注意：数组公式的结果长度必须与 fn 一致；最终结果必须是有限标量。
"""


DEFAULT_FORMULAS = {
    # ==================== PowerSum 串扰公式 ====================
    'PSFEXT': '10*log10(psum(pow(10,RAW_FEXT_dB/10)))',
    'PSNEXT': '10*log10(psum(pow(10,RAW_NEXT_dB/10)))',
    'PSXT': '10*log10(pow(10,PSFEXT/10)+pow(10,PSNEXT/10))',

    # ==================== ICN 标量中间量 ====================
    'deltaf': 'fstep',
    'fr': '1.5*(fb/2)',
    'ft_n': '0.2365/Tnt',
    'ft_f': '0.2365/Tft',
    'sf': '(PAM+1)/(3*(PAM-1))',

    # ==================== 频谱权重与信道损耗 ====================
    'Wnt': 'sf*(Ant*Ant/(fb))*pow(sin(pi*(fn/fb))/(pi*(fn/fb)),2)*(1/(1+pow(fn/ft_n,4)))*(1/(1+pow(fn/fr,8)))',
    'Wft': 'sf*(Aft*Aft/(fb))*pow(sin(pi*(fn/fb))/(pi*(fn/fb)),2)*(1/(1+pow(fn/ft_f,4)))*(1/(1+pow(fn/fr,8)))',
    'ChannelLoss_n': 'pow(10,(-2*ILn*fn/fb)/10)',
    'ChannelLoss_f': 'pow(10,(-2*ILf*fn/fb)/10)',

    # ==================== ICN / ccICN 最终结果 ====================
    'ICN_n': 'sqrt(2*deltaf*sum(Wnt*pow(10,PSNEXT/10)))',
    'ICN_f': 'sqrt(2*deltaf*sum(Wft*pow(10,PSFEXT/10)))',
    'ICN': 'sqrt(ICN_n*ICN_n+ICN_f*ICN_f)',
    'ccICN_n': 'sqrt(2*deltaf*sum(Wnt*pow(10,PSNEXT/10)*ChannelLoss_n))',
    'ccICN_f': 'sqrt(2*deltaf*sum(Wft*pow(10,PSFEXT/10)*ChannelLoss_f))',
    'ccICN': 'sqrt(ccICN_n*ccICN_n+ccICN_f*ccICN_f)',
}
