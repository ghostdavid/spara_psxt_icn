import ast
import os

import numpy as np


def devices():
    os.environ['PYOPENCL_NO_CACHE'] = '1'
    import pyopencl as cl
    found = []
    for platform in cl.get_platforms():
        for device in platform.get_devices(device_type=cl.device_type.GPU):
            key = f'{platform.name.strip()} | {device.name.strip()}'
            found.append((key, device))
    return found


class OpenCLBackend:
    def __init__(self, selected=''):
        import pyopencl as cl
        candidates = devices()
        if selected and selected != '自动':
            candidates = [(key, dev) for key, dev in candidates if key == selected]
        candidates = [(key, dev) for key, dev in candidates if dev.double_fp_config]
        if not candidates:
            raise RuntimeError('没有支持双精度的 OpenCL GPU')
        self.name, device = candidates[0]
        self.cl = cl
        self.context = cl.Context([device])
        self.queue = cl.CommandQueue(self.context)
        self.programs = {}
        self.chunk_bytes = min(32 * 1024 * 1024, device.max_mem_alloc_size // 4)

    def run(self, source, inputs, shape):
        cl = self.cl
        arrays = [np.ascontiguousarray(a, dtype=np.float64) for a in inputs]
        buffers = [cl.Buffer(self.context, cl.mem_flags.READ_ONLY |
                            cl.mem_flags.COPY_HOST_PTR, hostbuf=a) for a in arrays]
        result = np.empty(shape, dtype=np.float64)
        if not result.size:
            return result
        output = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY, result.nbytes)
        if source not in self.programs:
            self.programs[source] = cl.Program(self.context, source).build()
        kernel = cl.Kernel(self.programs[source], 'compute')
        kernel(self.queue, (result.size,), None, *buffers, output).wait()
        cl.enqueue_copy(self.queue, result, output).wait()
        return result

    def interpolate(self, x, values, target, check):
        flat = values.reshape(-1, len(x))
        out = np.empty((len(flat), len(target)), dtype=np.complex128)
        n, m = len(x), len(target)
        source = '''
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
double delta(__global const double *x, __global const double *y, int i) {
 return (y[i+1]-y[i])/(x[i+1]-x[i]);
}
double slope(__global const double *x, __global const double *y, int i, int n) {
 if(n==2) return delta(x,y,0);
 if(i==0 || i==n-1) {
  int a=i==0?0:n-2, b=i==0?1:n-3;
  double h0=x[a+1]-x[a], h1=x[b+1]-x[b];
  double d0=delta(x,y,a), d1=delta(x,y,b);
  double d=((2*h0+h1)*d0-h0*d1)/(h0+h1);
  if(sign(d)!=sign(d0)) return 0;
  if(sign(d0)!=sign(d1) && fabs(d)>fabs(3*d0)) return 3*d0;
  return d;
 }
 double a=delta(x,y,i-1), b=delta(x,y,i);
 if(a==0 || b==0 || sign(a)!=sign(b)) return 0;
 double h0=x[i]-x[i-1], h1=x[i+1]-x[i];
 double w1=2*h1+h0, w2=h1+2*h0;
 return (w1+w2)/(w1/a+w2/b);
}
__kernel void compute(__global const double *x, __global const double *values,
 __global const double *target, __global double *out) {
 int g=get_global_id(0), n=NPOINTS, m=MPOINTS;
 __global const double *y=values+(g/m)*n;
 double t=target[g%m];
 if(t<=x[0]) {out[g]=y[0];return;}
 if(t>=x[n-1]) {out[g]=y[n-1];return;}
 int lo=0, hi=n-1;
 while(hi-lo>1) {int mid=(lo+hi)/2; if(x[mid]<=t) lo=mid;else hi=mid;}
 double h=x[hi]-x[lo], s=t-x[lo], d=delta(x,y,lo);
 double a=slope(x,y,lo,n), b=slope(x,y,hi,n);
 double c=(a+b-2*d)/h;
 out[g]=y[lo]+s*(a+s*((d-a)/h-c+s*c/h));
}
'''.replace('NPOINTS', str(n)).replace('MPOINTS', str(m))
        width = max(1, self.chunk_bytes // max(8 * n, 8 * m))
        for start in range(0, len(flat), width):
            check()
            stop = min(start + width, len(flat))
            for component in ('real', 'imag'):
                getattr(out[start:stop], component)[:] = self.run(
                    source, [x, getattr(flat[start:stop], component), target],
                    (stop-start, m))
        return out.reshape(values.shape[:2] + (m,))

    def evaluate(self, expression, env):
        from sparam_core import _EXPR_CONSTS, _EXPR_FUNCS
        try:
            tree = ast.parse(expression, mode='eval')
        except (SyntaxError, RecursionError) as exc:
            raise ValueError(f'表达式无效：{exc}') from exc
        if len(expression) > 5000:
            raise ValueError('表达式过长')
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Expression, ast.Constant, ast.Name, ast.Load,
                                     ast.BinOp, ast.UnaryOp, ast.Call, ast.Add, ast.Sub,
                                     ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub)):
                raise ValueError('不允许的表达式元素')
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name)
                    or node.func.id not in _EXPR_FUNCS or node.keywords):
                raise ValueError('不允许的函数调用')
            if isinstance(node, ast.Constant) and (isinstance(node.value, bool)
                    or not isinstance(node.value, (int, float))):
                raise ValueError('不允许的常量')

        def visit(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                if node.id in env:
                    return env[node.id]
                if node.id in _EXPR_CONSTS:
                    return _EXPR_CONSTS[node.id]
                raise ValueError(f'未知变量: {node.id}')
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                return value if isinstance(node.op, ast.UAdd) else -value
            if isinstance(node, ast.BinOp):
                args = [visit(node.left), visit(node.right)]
                expressions = {ast.Add: '(a+b)', ast.Sub: '(a-b)',
                               ast.Mult: '(a*b)', ast.Div: '(a/b)', ast.Pow: 'pow(a,b)'}
                return self.elementwise(expressions[type(node.op)], args)
            if isinstance(node, ast.Call):
                name = node.func.id
                args = [visit(arg) for arg in node.args]
                if name in ('sum', 'psum', 'min', 'max'):
                    return self.reduce(name, args[0])
                if all(np.ndim(arg) == 0 for arg in args):
                    return _EXPR_FUNCS[name](*args)
                name = {'abs': 'fabs'}.get(name, name)
                return self.elementwise(f'{name}({",".join("ab"[:len(args)])})', args)
            raise ValueError('不支持的 GPU 表达式')
        return visit(tree.body)

    def elementwise(self, expr, args):
        arrays = np.broadcast_arrays(*args)
        shape = arrays[0].shape
        signature = ', '.join(f'__global const double *p{i}' for i in range(len(arrays)))
        variables = ''.join(f'double {name}=p{i}[g];' for i, name in enumerate('ab'[:len(arrays)]))
        source = ('#pragma OPENCL EXTENSION cl_khr_fp64 : enable\n'
                  f'__kernel void compute({signature}, __global double *out) {{'
                  f'int g=get_global_id(0);{variables}out[g]={expr};}}')
        result = np.empty(shape, dtype=np.float64)
        width = max(1, self.chunk_bytes // 8)
        flat = [a.ravel() for a in arrays]
        for start in range(0, result.size, width):
            stop = min(start + width, result.size)
            result.ravel()[start:stop] = self.run(source, [a[start:stop] for a in flat], (stop-start,))
        return result

    def reduce(self, name, value):
        value = np.asarray(value, dtype=np.float64)
        if name == 'psum' and value.ndim > 1:
            rows, cols = value.shape[0], int(np.prod(value.shape[1:]))
            shape = value.shape[1:]
        else:
            rows, cols, shape = value.size, 1, ()
        if not rows:
            if name in ('sum', 'psum'):
                return np.zeros(shape)
            raise ValueError('空数组不能取最值')
        initial = {'min': 'INFINITY', 'max': '-INFINITY'}.get(name, '0')
        operation = {'min': 'v=fmin(v,a)', 'max': 'v=fmax(v,a)'}.get(name, 'v+=a')
        source = ('#pragma OPENCL EXTENSION cl_khr_fp64 : enable\n'
                  '__kernel void compute(__global const double *p, __global double *out) {'
                  f'int g=get_global_id(0);double v={initial};'
                  f'for(int r=0;r<{rows};r++){{double a=p[r*{cols}+g];{operation};}}out[g]=v;}}')
        return self.run(source, [value], shape)
