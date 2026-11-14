import importlib.abc
import importlib.util
import os
import sys
import types
from pathlib import Path


_ADAPTATIONS = {
    'matplotlib': {
        '_get_config_or_cache_dir': '''
def _get_config_or_cache_dir(xdg_base_getter):
    return str(Path(__file__).resolve().parent / 'mpl-data')
''',
    },
    'matplotlib.font_manager': {
        'json_dump': '''
def json_dump(data, filename):
    return None
''',
    },
}


class _ReadOnlyLoader(importlib.abc.Loader):
    def __init__(self, loader, name):
        self.loader = loader
        self.name = name

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        code = self.loader.get_code(self.name)
        replacements = {}
        for name, source in _ADAPTATIONS[self.name].items():
            compiled = compile(source, code.co_filename, 'exec')
            replacements[name] = next(
                item for item in compiled.co_consts
                if isinstance(item, types.CodeType) and item.co_name == name)
        found = set()
        constants = []
        for item in code.co_consts:
            if isinstance(item, types.CodeType) and item.co_name in replacements:
                found.add(item.co_name)
                item = replacements[item.co_name]
            constants.append(item)
        if found != set(replacements):
            raise RuntimeError(f'不兼容的 Matplotlib，只读适配失败: {self.name}')
        exec(code.replace(co_consts=tuple(constants)), module.__dict__)

    def __getattr__(self, name):
        return getattr(self.loader, name)


class _ReadOnlyFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _ADAPTATIONS:
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                spec.loader = _ReadOnlyLoader(spec.loader, fullname)
                return spec
        return None


_matplotlib = None


def load_matplotlib():
    global _matplotlib
    if _matplotlib is not None:
        return _matplotlib
    if 'matplotlib' in sys.modules:
        raise RuntimeError('Matplotlib 必须通过只读加载入口初始化')
    sys.dont_write_bytecode = True
    spec = importlib.util.find_spec('matplotlib')
    resources = Path(spec.origin).resolve().parent / 'mpl-data'
    os.environ['MPLCONFIGDIR'] = str(resources)
    os.environ['MATPLOTLIBRC'] = str(resources / 'matplotlibrc')
    os.environ['MPLBACKEND'] = 'TkAgg'
    finder = _ReadOnlyFinder()
    sys.meta_path.insert(0, finder)
    previous = Path.cwd()
    try:
        os.chdir(resources)
        import matplotlib
        if matplotlib.__version__ != '3.11.1':
            raise RuntimeError('只读绘图适配要求 matplotlib==3.11.1')
        from matplotlib import font_manager
        matplotlib.rcdefaults()
        matplotlib.use('TkAgg')
        _matplotlib = matplotlib
        return matplotlib
    finally:
        os.chdir(previous)
        sys.meta_path.remove(finder)
